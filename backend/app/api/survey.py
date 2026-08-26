"""Structures, interview sessions, answer review and document export."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
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
from app.ai import engine, llm
from app.db.models import Answer, ChatMessage, Export, Structure, SurveySession, utcnow
from app.db.session import get_db
from app.pca.blueprint import TEMPLATE_FILES, Question, get_plan, sections
from app.pca.docx_filler import fill_document
from app.schemas.api import (
    AnswerOut,
    AnswerOverride,
    ChatResponse,
    ConfirmRequest,
    ContactCard,
    ExportOut,
    MessageOut,
    PendingAnswer,
    ProgressSection,
    QuestionOut,
    SessionCreateRequest,
    SessionDetail,
    SessionState,
    StructureOut,
)

router = APIRouter(tags=["survey"])

TEMPLATE_LABEL = {
    "dsi": "Etat des lieux - Direction des Systemes d'Information",
    "entite": "Etat des lieux - Entite",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _structure_out(structure: Structure) -> StructureOut:
    return StructureOut(
        id=structure.id,
        code=structure.code,
        name=structure.name,
        parent=structure.parent,
        template_kind=structure.template_kind,
    )


def _question_out(question: Question, index: int, total: int) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        kind=question.kind,
        section=question.section,
        label=question.label,
        prompt=question.prompt,
        help=question.help,
        example=question.example,
        columns=[
            {
                "id": c.id,
                "label": c.label,
                "hint": c.hint,
                "choices": c.choices,
                "required": c.required,
            }
            for c in question.columns
        ],
        index=index,
        total=total,
    )


def _answer_map(db: Session, survey: SurveySession) -> Dict[str, Answer]:
    rows = db.execute(select(Answer).where(Answer.session_id == survey.id)).scalars()
    return {a.question_id: a for a in rows}


def build_state(
    db: Session, survey: SurveySession, degraded: bool = False, engine_label: str = ""
) -> SessionState:
    plan = get_plan(survey.template_kind)
    total = len(plan)
    answers = _answer_map(db, survey)
    # A draft awaiting confirmation is not progress: the interviewee has not
    # yet seen it laid out, so it may still be wrong.
    filled = {qid for qid, a in answers.items() if a.confirmed and a.completeness != "vide"}

    cursor = max(0, min(survey.cursor, total))
    question = _question_out(plan[cursor], cursor, total) if cursor < total else None

    progress: List[ProgressSection] = []
    active_section = plan[cursor].section if cursor < total else None
    for title in sections(survey.template_kind):
        in_section = [q for q in plan if q.section == title]
        progress.append(
            ProgressSection(
                title=title,
                total=len(in_section),
                answered=sum(1 for q in in_section if q.id in filled),
                active=title == active_section,
            )
        )

    return SessionState(
        id=survey.id,
        structure=_structure_out(survey.structure),
        template_kind=survey.template_kind,
        status=survey.status,
        cursor=cursor,
        total=total,
        answered=len(filled),
        percent=int(round(100 * len(filled) / total)) if total else 0,
        question=question,
        sections=progress,
        degraded=degraded,
        engine=engine_label or llm.active_label(),
    )


def _message_out(dek: bytes, session_id: str, row: ChatMessage) -> MessageOut:
    return MessageOut(
        id=row.id,
        role=row.role,
        body=open_json(dek, session_id, f"msg:{row.id}", row.body_enc),
        intent=row.intent,
        created_at=deps._aware(row.created_at).isoformat(),
    )


def append_message(
    db: Session, survey: SurveySession, dek: bytes, role: str, body: str,
    intent: Optional[str] = None, question_id: Optional[str] = None,
) -> ChatMessage:
    next_seq = (
        db.execute(
            select(func.coalesce(func.max(ChatMessage.seq), 0)).where(
                ChatMessage.session_id == survey.id
            )
        ).scalar_one()
        + 1
    )
    row = ChatMessage(
        session_id=survey.id, seq=next_seq, role=role, intent=intent, question_id=question_id,
        body_enc="",
    )
    db.add(row)
    db.flush()  # need the id before sealing: it is part of the AAD
    row.body_enc = seal_json(dek, survey.id, f"msg:{row.id}", body)
    return row


def store_answer(
    db: Session, survey: SurveySession, dek: bytes, question: Question,
    payload: Dict[str, Any], completeness: str, confirmed: bool = False,
) -> None:
    existing = db.execute(
        select(Answer).where(Answer.session_id == survey.id, Answer.question_id == question.id)
    ).scalar_one_or_none()

    sealed = seal_json(dek, survey.id, f"answer:{question.id}", payload)
    if existing is None:
        db.add(
            Answer(
                session_id=survey.id, question_id=question.id, kind=question.kind,
                payload_enc=sealed, completeness=completeness, confirmed=confirmed,
            )
        )
    else:
        existing.payload_enc = sealed
        existing.completeness = completeness
        existing.confirmed = confirmed
        existing.revision += 1
        existing.updated_at = utcnow()


def read_answer(dek: bytes, survey_id: str, row: Optional[Answer]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return open_json(dek, survey_id, f"answer:{row.question_id}", row.payload_enc)


# --------------------------------------------------------------------------- #
# Structures
# --------------------------------------------------------------------------- #
@router.get("/structures", response_model=List[StructureOut])
def list_structures(
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> List[StructureOut]:
    stmt = select(Structure).where(Structure.is_active.is_(True)).order_by(Structure.name)
    rows = list(db.execute(stmt).scalars())

    allowed = principal.user.allowed_structures
    if allowed and principal.role == "client":
        codes = {c.strip() for c in allowed.split(",") if c.strip()}
        rows = [r for r in rows if r.code in codes]
    return [_structure_out(r) for r in rows]


@router.get("/contact", response_model=ContactCard)
def contact_card() -> ContactCard:
    return ContactCard(
        name=settings.CONTACT_NAME, email=settings.CONTACT_EMAIL, phone=settings.CONTACT_PHONE
    )


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
@router.get("/sessions", response_model=List[SessionState])
def list_sessions(
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> List[SessionState]:
    stmt = (
        select(SurveySession)
        .where(SurveySession.user_id == principal.id)
        .order_by(SurveySession.last_activity_at.desc())
    )
    return [build_state(db, s) for s in db.execute(stmt).scalars()]


@router.post("/sessions", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> SessionDetail:
    if principal.user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mot de passe a renouveler.")

    structure = db.get(Structure, payload.structure_id)
    if structure is None or not structure.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure inconnue.")

    allowed = principal.user.allowed_structures
    if allowed and principal.role == "client":
        codes = {c.strip() for c in allowed.split(",") if c.strip()}
        if structure.code not in codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'etes pas habilite a documenter cette structure.",
            )

    # Resume rather than duplicate an interview already in progress.
    existing = db.execute(
        select(SurveySession).where(
            SurveySession.user_id == principal.id,
            SurveySession.structure_id == structure.id,
            SurveySession.status == "in_progress",
        )
    ).scalar_one_or_none()
    if existing is not None:
        return get_session(existing.id, db, principal)

    dek = new_dek()
    survey = SurveySession(
        user_id=principal.id,
        structure_id=structure.id,
        template_kind=structure.template_kind,
        wrapped_dek=wrap_dek(dek),
    )
    db.add(survey)
    db.flush()

    plan = get_plan(survey.template_kind)
    append_message(
        db, survey, dek, "assistant",
        engine.greeting(structure.name, len(plan), plan[0].prompt),
        intent="systeme", question_id=plan[0].id,
    )
    audit.record(
        db, action="survey.start", actor_id=principal.id, target=survey.id,
        ip=ratelimit.client_ip(request), meta={"structure": structure.code, "questions": len(plan)},
    )
    db.commit()
    db.refresh(survey)
    return get_session(survey.id, db, principal)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> SessionDetail:
    survey = deps.load_active_session(db, principal.id, session_id)
    dek = unwrap_dek(survey.wrapped_dek)

    rows = db.execute(
        select(ChatMessage).where(ChatMessage.session_id == survey.id).order_by(ChatMessage.seq)
    ).scalars()
    return SessionDetail(
        state=build_state(db, survey),
        messages=[_message_out(dek, survey.id, r) for r in rows],
    )


# --------------------------------------------------------------------------- #
# Answer review / manual correction
# --------------------------------------------------------------------------- #
@router.get("/sessions/{session_id}/answers", response_model=List[AnswerOut])
def list_answers(
    session_id: str,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> List[AnswerOut]:
    survey = deps.load_active_session(db, principal.id, session_id)
    dek = unwrap_dek(survey.wrapped_dek)
    stored = _answer_map(db, survey)

    out: List[AnswerOut] = []
    for question in get_plan(survey.template_kind):
        row = stored.get(question.id)
        payload = read_answer(dek, survey.id, row) or {}
        out.append(
            AnswerOut(
                question_id=question.id,
                label=question.label,
                section=question.section,
                kind=question.kind,
                completeness=row.completeness if row else "vide",
                confirmed=bool(row.confirmed) if row else False,
                value=payload.get("value"),
                rows=payload.get("rows"),
            )
        )
    return out


@router.put("/sessions/{session_id}/answers", response_model=AnswerOut)
def override_answer(
    session_id: str,
    payload: AnswerOverride,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> AnswerOut:
    """Direct edit from the review panel. The model is not involved."""
    survey = deps.load_active_session(db, principal.id, session_id)
    dek = unwrap_dek(survey.wrapped_dek)

    question = next(
        (q for q in get_plan(survey.template_kind) if q.id == payload.question_id), None
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question inconnue.")

    body, completeness = _clean_payload(question, payload.value, payload.rows)

    store_answer(db, survey, dek, question, body, completeness, confirmed=True)
    survey.last_activity_at = utcnow()

    # A correction made from the rail is part of the conversation: without this
    # the transcript would still show the superseded answer and nothing else.
    summary = (
        f"{len(body['rows'])} ligne(s)" if question.kind == "grid"
        else (body["value"][:160] + ("…" if len(body["value"]) > 160 else ""))
    )
    append_message(
        db, survey, dek, "assistant",
        f"Correction enregistree pour « {question.label} » :\n\n{summary}",
        intent="correction", question_id=question.id,
    )

    audit.record(
        db, action="survey.answer_override", actor_id=principal.id, target=survey.id,
        ip=ratelimit.client_ip(request), meta={"question_id": question.id},
    )
    db.commit()

    return AnswerOut(
        question_id=question.id, label=question.label, section=question.section,
        kind=question.kind, completeness=completeness,
        value=body.get("value"), rows=body.get("rows"),
    )


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(text: str) -> str:
    return _SAFE.sub("_", text).strip("_")[:60] or "entite"


@router.post("/sessions/{session_id}/export", response_model=ExportOut)
def export_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> ExportOut:
    ratelimit.enforce(request, "export", settings.RL_EXPORT, subject=principal.id)
    survey = deps.load_active_session(db, principal.id, session_id)
    dek = unwrap_dek(survey.wrapped_dek)

    # Only confirmed answers reach the client's document. A draft the
    # interviewee never validated must not appear in a deliverable.
    answers = {
        qid: read_answer(dek, survey.id, row) or {}
        for qid, row in _answer_map(db, survey).items()
        if row.confirmed
    }
    if not answers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Aucune reponse enregistree : le document serait vide.",
        )

    template_path = os.path.join(settings.TEMPLATE_DIR, TEMPLATE_FILES[survey.template_kind])
    document = fill_document(
        template_path,
        survey.template_kind,
        answers,
        structure_name=survey.structure.name,
        structure_code=survey.structure.code,
        redacteur=f"{principal.user.full_name} - via plateforme Devoteam",
        interview_date=deps._aware(survey.started_at).date(),
    )

    digest = hashlib.sha256(document).hexdigest()
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)

    record = Export(
        session_id=survey.id,
        filename=(
            f"Etat_des_lieux_{_safe_name(survey.structure.name)}_"
            f"{dt.date.today().isoformat()}.docx"
        ),
        blob_path="",
        sha256=digest,
        size_bytes=len(document),
    )
    db.add(record)
    db.flush()

    # The generated document is confidential too: it is sealed on disk.
    record.blob_path = os.path.join(settings.EXPORT_DIR, f"{record.id}.bin")
    with open(record.blob_path, "wb") as handle:
        handle.write(encrypt_bytes(dek, survey.id, f"export:{record.id}", document))

    if survey.status != "completed":
        survey.status = "completed"
        survey.completed_at = utcnow()

    audit.record(
        db, action="survey.export", actor_id=principal.id, target=survey.id,
        ip=ratelimit.client_ip(request),
        meta={"export_id": record.id, "sha256": digest, "answers": len(answers)},
    )
    db.commit()

    return ExportOut(
        id=record.id,
        filename=record.filename,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        created_at=deps._aware(record.created_at).isoformat(),
        download_token=security_sign(record.id, principal.id),
    )


def security_sign(export_id: str, user_id: str) -> str:
    from app.core.security import sign_download

    return sign_download(export_id, user_id)


@router.get("/exports/{token}")
def download_export(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_password_set),
) -> Response:
    from app.core.security import verify_download

    parsed = verify_download(token)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lien expire ou invalide.")
    export_id, token_user = parsed
    if token_user != principal.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Lien non valide.")

    record = db.get(Export, export_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document introuvable.")

    survey = deps.load_active_session(db, principal.id, record.session_id)
    dek = unwrap_dek(survey.wrapped_dek)

    with open(record.blob_path, "rb") as handle:
        document = decrypt_bytes(dek, survey.id, f"export:{record.id}", handle.read())

    if hashlib.sha256(document).hexdigest() != record.sha256:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Le document a ete altere et ne peut pas etre servi.",
        )

    record.download_count += 1
    audit.record(
        db, action="survey.download", actor_id=principal.id, target=record.id,
        ip=ratelimit.client_ip(request), meta={"count": record.download_count},
    )
    db.commit()

    return Response(
        content=document,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{record.filename}"',
            "X-Content-Digest": f"sha256={record.sha256}",
            "Cache-Control": "no-store",
        },
    )


# --------------------------------------------------------------------------- #
# Verification: nothing reaches the document until the interviewee confirms it
# --------------------------------------------------------------------------- #
def pending_answer(question: Question, payload: Dict[str, Any]) -> PendingAnswer:
    """Lay an extraction out for the verification panel."""
    return PendingAnswer(
        question_id=question.id,
        label=question.label,
        section=question.section,
        kind=question.kind,
        prompt=question.prompt,
        help=question.help,
        example=question.example,
        columns=[
            {"id": c.id, "label": c.label, "hint": c.hint,
             "choices": c.choices, "required": c.required}
            for c in question.columns
        ],
        value=payload.get("value"),
        rows=payload.get("rows"),
    )


def _clean_payload(question: Question, value: Optional[str],
                   rows: Optional[List[Dict[str, str]]]) -> tuple[Dict[str, Any], str]:
    """Normalise an edited payload. Column names are fixed by the template."""
    if question.kind == "grid":
        allowed = {c.id for c in question.columns}
        clean_rows = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            # Unknown keys are dropped: the interviewee edits cells, never the
            # column set - those come from the client's own .docx.
            cells = {k: str(v or "").strip()[:2000] for k, v in row.items() if k in allowed}
            if any(cells.values()):
                clean_rows.append({c.id: cells.get(c.id, "") for c in question.columns})
        return {"rows": clean_rows}, ("complete" if clean_rows else "vide")

    text = (value or "").strip()[:8000]
    return {"value": text}, ("complete" if text else "vide")


@router.post("/sessions/{session_id}/confirm", response_model=ChatResponse)
def confirm_answer(
    session_id: str,
    payload: ConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> ChatResponse:
    """Validate the draft - as edited - and move the interview on."""
    from app.api.chat import _move_cursor

    survey = deps.load_active_session(db, principal.id, session_id)
    if survey.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cet entretien est cloture."
        )

    dek = unwrap_dek(survey.wrapped_dek)
    plan = get_plan(survey.template_kind)
    total = len(plan)

    question = next((q for q in plan if q.id == payload.question_id), None)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question inconnue.")

    body, completeness = _clean_payload(question, payload.value, payload.rows)
    if completeness == "vide":
        raise HTTPException(
            status_code=422,  # Unprocessable Content
            detail="La reponse est vide. Completez-la ou passez la question.",
        )

    store_answer(db, survey, dek, question, body, completeness, confirmed=True)

    cursor = min(plan.index(question) + 1, total)
    survey.cursor = cursor
    survey.followups = 0
    survey.last_activity_at = utcnow()

    completed = cursor >= total
    if completed:
        survey.status = "completed"
        survey.completed_at = utcnow()
        reply_text = f"C'est valide, merci.\n\n{engine.closing(survey.structure.name)}"
    else:
        reply_text = f"C'est valide, merci.\n\n{plan[cursor].prompt}"

    reply_row = append_message(
        db, survey, dek, "assistant", reply_text, intent="confirmation",
        question_id=plan[cursor].id if cursor < total else None,
    )
    audit.record(
        db, action="survey.answer_confirmed", actor_id=principal.id, target=survey.id,
        ip=ratelimit.client_ip(request),
        meta={"question_id": question.id, "completeness": completeness,
              "rows": None, "edited": True},
    )
    db.commit()
    db.refresh(reply_row)

    return ChatResponse(
        reply=_message_out(dek, survey.id, reply_row),
        state=build_state(db, survey),
        intent="confirmation",
        recorded=True,
        completed=completed,
    )


@router.post("/sessions/{session_id}/discard", response_model=ChatResponse)
def discard_draft(
    session_id: str,
    payload: ConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> ChatResponse:
    """Throw the draft away and stay on the question so it can be answered again."""
    survey = deps.load_active_session(db, principal.id, session_id)
    dek = unwrap_dek(survey.wrapped_dek)
    plan = get_plan(survey.template_kind)

    question = next((q for q in plan if q.id == payload.question_id), None)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question inconnue.")

    draft = db.execute(
        select(Answer).where(
            Answer.session_id == survey.id,
            Answer.question_id == question.id,
            Answer.confirmed.is_(False),
        )
    ).scalar_one_or_none()
    if draft is not None:
        db.delete(draft)

    survey.last_activity_at = utcnow()
    reply_row = append_message(
        db, survey, dek, "assistant",
        f"Tres bien, reprenons.\n\n{question.prompt}",
        intent="navigation", question_id=question.id,
    )
    audit.record(
        db, action="survey.draft_discarded", actor_id=principal.id, target=survey.id,
        ip=ratelimit.client_ip(request), meta={"question_id": question.id},
    )
    db.commit()
    db.refresh(reply_row)

    return ChatResponse(
        reply=_message_out(dek, survey.id, reply_row),
        state=build_state(db, survey),
        intent="navigation",
        recorded=False,
        completed=False,
    )
