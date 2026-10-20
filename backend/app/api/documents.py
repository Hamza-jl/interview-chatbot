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
from pydantic import BaseModel, Field
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
from app.ingest import extract, outbound, reader, understand, write_back
from app.ingest.slots import DocumentPlan, Slot
from app.schemas.api import SessionDetail

logger = logging.getLogger("pca.documents")

router = APIRouter(prefix="/documents", tags=["documents"])

# Generous enough for a real questionnaire, small enough that a mistaken upload
# of a video does not fill the disk. Lu depuis la configuration, et non fixé
# ici, parce que le middleware applique le même plafond en amont : deux valeurs
# séparées se seraient désynchronisées, et le refus serait venu du middleware
# avec un message qui ne parle pas du fichier.
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_BYTES


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


MAX_CONTEXT_CHARS = 4000


def read_context(document: UploadedDocument) -> str:
    """The briefing typed in for this document, unsealed."""
    if not document.context_enc:
        return ""
    dek = unwrap_dek(document.wrapped_dek)
    return open_json(dek, document.id, "context", document.context_enc) or ""


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
        "has_context": bool(document.context_enc),
        "cloud_model": document.cloud_model or "",
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
        # `extract` lit tout ce qui est lisible, pas seulement les quatre formats
        # remplissables : un scan ou un CSV produit un entretien valable, dont
        # les reponses sortiront dans un nouveau document.
        read = extract.read(staging, name)
        discovered = read.plan if read.plan is not None else DocumentPlan(
            filename=name, kind=read.kind, title=name, slots=[], notes=read.notes)
        cloud_text = read.text
        fillable = read.fillable
        images = read.images
    except extract.Unreadable as refused:
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
    # Le texte lisible est scelle a part : c'est lui, et lui seul, qui partira
    # si le consultant demande une analyse distante.
    document.source_text_enc = seal_json(
        dek, document.id, "source_text",
        {"text": cloud_text, "fillable": fillable, "images": images})

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
# The briefing
# --------------------------------------------------------------------------- #
class ContextIn(BaseModel):
    context: str = Field(default="", max_length=MAX_CONTEXT_CHARS)


@router.put("/{document_id}/context")
def set_context(
    document_id: str,
    payload: ContextIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> Dict[str, Any]:
    """Save what the consultant knows that the document does not say.

    A blank template cannot say which entity is being interviewed, how big it
    is, or what changed since last year - and that is exactly what turns
    "Effectif ?" into a question worth asking. Written by hand because only the
    person running the interview knows it.

    Sealed, and stored against the document rather than the session: it is
    written before the interview exists, and it survives the interview being
    restarted.
    """
    document = _own(db, principal, document_id)
    text = payload.context.strip()

    dek = unwrap_dek(document.wrapped_dek)
    document.context_enc = seal_json(dek, document.id, "context", text) if text else ""

    # The wording was generated without it - or with an older version of it -
    # so it is now out of date. Saying so beats silently keeping stale questions.
    plan, wording = load_plan(document)
    stale = bool(wording)

    audit.record(
        db, action="document.context", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request), meta={"chars": len(text)},
    )
    db.commit()
    return {"id": document.id, "context": text, "questions_stale": stale}


# --------------------------------------------------------------------------- #
# Analyse par modele distant
# --------------------------------------------------------------------------- #
def _source_text(document: UploadedDocument) -> Dict[str, Any]:
    if not document.source_text_enc:
        return {"text": "", "fillable": False, "images": 0}
    dek = unwrap_dek(document.wrapped_dek)
    return open_json(dek, document.id, "source_text", document.source_text_enc) or {}


@router.get("/{document_id}/outbound")
def outbound_preview(
    document_id: str,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> Dict[str, Any]:
    """Exactement ce qui partirait, avant que quoi que ce soit ne parte.

    Un consultant qui voit un nom de client dans cet ecran peut l'ajouter aux
    termes a masquer et recommencer. C'est le seul moment ou cela coute encore
    quelque chose de s'en apercevoir.
    """
    from app.ai import openrouter

    document = _own(db, principal, document_id)
    source = _source_text(document)
    sent = outbound.prepare(document.filename, document.kind,
                            source.get("text", ""), images=source.get("images", 0))
    return {
        "id": document.id,
        "available": openrouter.available(),
        "models": openrouter.models(),
        "fillable": bool(source.get("fillable")),
        "summary": sent.summary(),
        "redactions": sent.redactions,
        "truncated": sent.truncated,
        "chars": sent.size_chars,
        "text": sent.text[:12000],
    }


@router.post("/{document_id}/understand")
def understand_remotely(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> Dict[str, Any]:
    """Envoie le fichier au modele distant et enregistre ce qu'il a compris."""
    from app.ai import openrouter

    document = _own(db, principal, document_id)
    if not openrouter.available():
        raise HTTPException(
            status_code=409,
            detail="L'analyse distante n'est pas activée sur ce serveur.")

    source = _source_text(document)
    extraction = extract.Extraction(
        kind=document.kind, text=source.get("text", ""),
        fillable=bool(source.get("fillable")), images=source.get("images", 0),
        plan=load_plan(document)[0] if document.plan_enc else None,
    )

    try:
        result = understand.understand(extraction, document.filename)
    except outbound.OutboundRefused as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    except openrouter.OpenRouterUnavailable as down:
        raise HTTPException(status_code=503, detail=str(down)) from down

    dek = unwrap_dek(document.wrapped_dek)
    document.plan_enc = seal_json(dek, document.id, "plan",
                                  _plan_to_json(result.plan, {}))
    document.title = (result.plan.title or document.filename)[:300]
    document.slot_count = len(result.plan.slots)
    document.grid_count = len(result.plan.grids)
    document.cloud_model = result.model[:120]
    ingest_plan.forget(document.id)

    audit.record(
        db, action="document.understand", actor_id=principal.id, target=document.id,
        ip=ratelimit.client_ip(request),
        meta={"model": result.model, "attempts": result.attempts,
              "fields": len(result.plan.slots), "matched": result.matched,
              "invented": result.invented, "chars_sent": result.sent.size_chars,
              "redactions": result.sent.redactions},
    )
    db.commit()
    db.refresh(document)

    return {
        **_out(document),
        "model": result.model,
        "attempts": result.attempts,
        "seconds": result.seconds,
        "matched": result.matched,
        "invented": result.invented,
        "notes": result.plan.notes,
        "fields": [
            {"id": s.id, "kind": s.kind, "label": s.label, "section": s.section,
             "columns": s.columns, "writable": bool(s.target)}
            for s in result.plan.slots
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
    background = read_context(document)
    wording: Dict[str, Dict[str, str]] = {}
    for slot in plan.slots:
        generated = ingest_questions.generate(slot, backend, background)
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
        meta={"count": len(wording), "engine": getattr(backend, "name", "deterministe"),
              "context": len(background)},
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
        "context": read_context(document),
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
