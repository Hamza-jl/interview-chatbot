"""Upload a document, get an interview, get the document back filled.

The four steps are deliberately separate calls. Reading a file is fast and
deterministic; phrasing thirty questions with a local model is neither, and
holding an HTTP request open for two minutes while a laptop generates them makes
the upload look broken. So the upload returns what was *found* immediately, and
the wording arrives with the plan that is built from it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.core import audit, ratelimit
from app.core.config import settings
from app.core.crypto import (
    decrypt_bytes,
    encrypt_bytes,
    new_dek,
    open_json,
    seal_json,
    unwrap_dek,
    wrap_dek,
)
from app.db.models import Answer, SurveySession, UploadedDocument, utcnow
from app.db.session import get_db
from app.ingest import plan as ingest_plan
from app.ingest import questions as ingest_questions
from app.ingest import reader, write_back
from app.ingest.slots import DocumentPlan, Slot
from app.schemas.api import SessionDetail

logger = logging.getLogger("pca.documents")

router = APIRouter(prefix="/documents", tags=["documents"])

# Generous enough for a real questionnaire, small enough that a mistaken upload
# of a video does not fill the disk.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _upload_dir() -> str:
    path = os.path.join(settings.EXPORT_DIR, "uploads")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------- #
# Serialising a plan
# --------------------------------------------------------------------------- #
def _plan_to_json(plan: DocumentPlan, wording: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    return {
        "filename": plan.filename,
        "kind": plan.kind,
        "title": plan.title,
        "notes": plan.notes,
        "slots": [
            {
                "id": s.id,
                "kind": s.kind,
                "label": s.label,
                "context": s.context,
                "columns": s.columns,
                "existing": s.existing,
                "min_rows": s.min_rows,
                "target": s.target,
            }
            for s in plan.slots
        ],
        "wording": wording,
    }


def _plan_from_json(data: Dict[str, Any]) -> DocumentPlan:
    return DocumentPlan(
        filename=data["filename"],
        kind=data["kind"],
        title=data.get("title", ""),
        notes=list(data.get("notes") or []),
        slots=[
            Slot(
                id=s["id"],
                kind=s["kind"],
                label=s["label"],
                target=s["target"],
                context=list(s.get("context") or []),
                columns=list(s.get("columns") or []),
                existing=s.get("existing"),
                min_rows=s.get("min_rows", 1),
            )
            for s in data.get("slots") or []
        ],
    )


def load_plan(document: UploadedDocument) -> tuple[DocumentPlan, Dict[str, Dict[str, str]]]:
    dek = unwrap_dek(document.wrapped_dek)
    data = open_json(dek, document.id, "plan", document.plan_enc)
    return _plan_from_json(data), data.get("wording") or {}


def ensure_registered(document: UploadedDocument) -> str:
    """Put the plan back in `blueprint.PLANS` after a restart.

    The registry is in memory, so a session opened yesterday would otherwise
    find no questions today.
    """
    if not ingest_plan.is_registered(document.id):
        plan, wording = load_plan(document)
        ingest_plan.build(document.id, plan, wording)
    return ingest_plan.template_kind(document.id)


def _out(document: UploadedDocument) -> Dict[str, Any]:
    return {
        "id": document.id,
        "filename": document.filename,
        "kind": document.kind,
        "title": document.title,
        "slots": document.slot_count,
        "grids": document.grid_count,
        "size_bytes": document.size_bytes,
        "created_at": deps._aware(document.created_at).isoformat(),
    }


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> Dict[str, Any]:
    ratelimit.enforce(request, "export", settings.RL_EXPORT, subject=principal.id)

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fichier trop volumineux (maximum {MAX_UPLOAD_BYTES // 1024 // 1024} Mo).",
        )
    if not payload:
        raise HTTPException(status_code=400, detail="Fichier vide.")

    name = os.path.basename(file.filename or "document")
    dek = new_dek()
    document = UploadedDocument(
        user_id=principal.id,
        filename=name,
        kind="?",
        wrapped_dek=wrap_dek(dek),
        blob_path="",
        plan_enc="",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    db.add(document)
    db.flush()

    # Written to a temporary path because every reader takes a filename: the
    # libraries stream from disk rather than memory.
    staging = os.path.join(_upload_dir(), f"{document.id}.incoming")
    with open(staging, "wb") as handle:
        handle.write(payload)

    try:
        discovered = reader.read(staging, name)
    except reader.UnsupportedDocument as refused:
        os.remove(staging)
        db.rollback()
        raise HTTPException(status_code=415, detail=str(refused)) from refused
    except Exception as exc:                                   # noqa: BLE001
        os.remove(staging)
        db.rollback()
        logger.exception("could not read %s", name)
        raise HTTPException(
            status_code=422,
            detail="Ce fichier n'a pas pu être lu. Il est peut-être protégé ou endommagé.",
        ) from exc
    finally:
        if os.path.exists(staging):
            os.remove(staging)

    document.kind = discovered.kind
    document.title = (discovered.title or name)[:300]
    document.slot_count = len(discovered.slots)
    document.grid_count = len(discovered.grids)

    document.blob_path = os.path.join(_upload_dir(), f"{document.id}.bin")
    with open(document.blob_path, "wb") as handle:
        handle.write(encrypt_bytes(dek, document.id, "source", payload))

    document.plan_enc = seal_json(dek, document.id, "plan", _plan_to_json(discovered, {}))

    audit.record(
        db, action="document.upload", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request),
        meta={"kind": discovered.kind, "slots": len(discovered.slots),
              "grids": len(discovered.grids), "bytes": len(payload)},
    )
    db.commit()
    db.refresh(document)

    return {
        **_out(document),
        "notes": discovered.notes,
        "preview": [
            {"id": s.id, "kind": s.kind, "label": s.label,
             "section": s.section, "columns": s.columns}
            for s in discovered.slots[:40]
        ],
    }


# --------------------------------------------------------------------------- #
# Wording
# --------------------------------------------------------------------------- #
@router.post("/{document_id}/questions")
def write_questions(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> Dict[str, Any]:
    """Phrase a question for every discovered blank. Slow on purpose - local."""
    document = _own(db, principal, document_id)
    plan, existing = load_plan(document)
    if not plan.slots:
        raise HTTPException(status_code=409, detail="Ce document n'a aucun champ à remplir.")

    from app.ai import llm

    backend = llm.active_backend()
    wording: Dict[str, Dict[str, str]] = {}
    for slot in plan.slots:
        generated = ingest_questions.generate(slot, backend)
        wording[slot.id] = {
            "question": generated.question,
            "aide": generated.help,
            "exemple": generated.example,
        }

    dek = unwrap_dek(document.wrapped_dek)
    document.plan_enc = seal_json(dek, document.id, "plan", _plan_to_json(plan, wording))
    ingest_plan.build(document.id, plan, wording)

    audit.record(
        db, action="document.questions", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request),
        meta={"count": len(wording), "engine": getattr(backend, "name", "deterministe")},
    )
    db.commit()

    return {
        "id": document.id,
        "questions": [
            {"id": s.id, "kind": s.kind, "label": s.label, "section": s.section,
             "columns": s.columns, **wording[s.id]}
            for s in plan.slots
        ],
    }


# --------------------------------------------------------------------------- #
# Listing and reading
# --------------------------------------------------------------------------- #
def _own(db: Session, principal: deps.Principal, document_id: str) -> UploadedDocument:
    document = db.get(UploadedDocument, document_id)
    if document is None or document.user_id != principal.id:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    return document


@router.get("")
def listing(
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(UploadedDocument)
        .where(UploadedDocument.user_id == principal.id)
        .order_by(UploadedDocument.created_at.desc())
    ).scalars()
    return [_out(d) for d in rows]


@router.get("/{document_id}")
def detail(
    document_id: str,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> Dict[str, Any]:
    document = _own(db, principal, document_id)
    plan, wording = load_plan(document)
    return {
        **_out(document),
        "notes": plan.notes,
        "questions": [
            {"id": s.id, "kind": s.kind, "label": s.label, "section": s.section,
             "columns": s.columns, **(wording.get(s.id) or {})}
            for s in plan.slots
        ],
    }


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> None:
    document = _own(db, principal, document_id)
    if document.blob_path and os.path.exists(document.blob_path):
        os.remove(document.blob_path)
    ingest_plan.forget(document.id)
    audit.record(
        db, action="document.delete", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request),
    )
    db.delete(document)
    db.commit()


# --------------------------------------------------------------------------- #
# The interview
# --------------------------------------------------------------------------- #
@router.post("/{document_id}/session", response_model=SessionDetail,
             status_code=status.HTTP_201_CREATED)
def open_interview(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> SessionDetail:
    """Start - or resume - the interview that fills this document.

    Deliberately not routed through `create_session`: that one enforces a single
    interview per *entity*, which is right for the état des lieux and wrong here.
    A user may upload ten documents; the equivalent rule is one interview per
    document, and that is what is enforced below.
    """
    from app.api.survey import append_message, get_session
    from app.db.models import Structure
    from app.pca.blueprint import get_plan

    document = _own(db, principal, document_id)
    kind = ensure_registered(document)
    plan = get_plan(kind)
    if not plan:
        raise HTTPException(
            status_code=409,
            detail="Les questions n'ont pas encore été rédigées pour ce document.",
        )

    existing = db.execute(
        select(SurveySession)
        .where(SurveySession.document_id == document.id,
               SurveySession.user_id == principal.id)
        .order_by(SurveySession.started_at.desc())
    ).scalars().first()
    if existing is not None:
        return get_session(existing.id, db, principal)

    # Every session needs a structure - the transcript, the progress screen and
    # the administrator's console all read its name. An uploaded file gets a
    # hidden one of its own, so it is named after the document rather than
    # borrowed from an entity it has nothing to do with.
    structure = Structure(
        code=f"DOC-{document.id[:10]}",
        name=(document.title or document.filename)[:200],
        parent="Document importé",
        template_kind=kind,
        is_active=False,
    )
    db.add(structure)
    db.flush()

    dek = new_dek()
    survey = SurveySession(
        user_id=principal.id,
        structure_id=structure.id,
        template_kind=kind,
        document_id=document.id,
        wrapped_dek=wrap_dek(dek),
    )
    db.add(survey)
    db.flush()

    append_message(
        db, survey, dek, "assistant",
        "Bonjour. J'ai lu « "
        + (document.title or document.filename)
        + f" » et j'y ai trouvé {document.slot_count} élément(s) à renseigner. "
        "Nous allons les parcourir ensemble, puis je vous rendrai votre fichier "
        "complété, dans sa mise en forme d'origine.",
    )
    append_message(db, survey, dek, "assistant", plan[0].prompt)

    audit.record(
        db, action="document.session", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request), meta={"session_id": survey.id},
    )
    db.commit()
    return get_session(survey.id, db, principal)


# --------------------------------------------------------------------------- #
# The filled file
# --------------------------------------------------------------------------- #
@router.post("/{document_id}/fill")
def fill(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> Dict[str, Any]:
    """Produce the uploaded file with every confirmed answer written in."""
    from app.api.survey import _answer_map, read_answer

    document = _own(db, principal, document_id)
    plan, _ = load_plan(document)
    kind = ensure_registered(document)

    survey = db.execute(
        select(SurveySession)
        .where(SurveySession.document_id == document.id,
               SurveySession.user_id == principal.id)
        .order_by(SurveySession.started_at.desc())
    ).scalars().first()
    if survey is None:
        raise HTTPException(status_code=409, detail="Aucun entretien ouvert sur ce document.")

    session_dek = unwrap_dek(survey.wrapped_dek)
    answers = {
        qid: read_answer(session_dek, survey.id, row) or {}
        for qid, row in _answer_map(db, survey).items()
        if row.confirmed
    }
    if not answers:
        raise HTTPException(
            status_code=409,
            detail="Aucune réponse confirmée : le document serait identique à l'original.",
        )

    dek = unwrap_dek(document.wrapped_dek)
    with open(document.blob_path, "rb") as handle:
        source = decrypt_bytes(dek, document.id, "source", handle.read())

    try:
        produced = write_back.fill(source, plan, answers)
    except write_back.WriteBackError as failure:
        raise HTTPException(status_code=422, detail=str(failure)) from failure

    from app.api.survey import security_sign
    from app.db.models import Export

    record = Export(
        session_id=survey.id,
        filename=f"rempli_{document.filename}",
        blob_path="",
        sha256=hashlib.sha256(produced).hexdigest(),
        size_bytes=len(produced),
    )
    db.add(record)
    db.flush()
    record.blob_path = os.path.join(settings.EXPORT_DIR, f"{record.id}.bin")
    with open(record.blob_path, "wb") as handle:
        handle.write(encrypt_bytes(session_dek, survey.id, f"export:{record.id}", produced))

    audit.record(
        db, action="document.fill", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request),
        meta={"answers": len(answers), "bytes": len(produced), "export": record.id},
    )
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "filename": record.filename,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "answers": len(answers),
        "blanks": len(plan.slots) - len(answers),
        "created_at": deps._aware(record.created_at).isoformat(),
        "download_token": security_sign(record.id, principal.id),
    }
