"""Administration surface: audit-chain verification and interview oversight.

Nothing here can read interview content - the endpoints expose counts, states
and integrity proofs only.
"""
from __future__ import annotations

import json

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import deps
from app.core import audit, ratelimit
from app.core.crypto import unwrap_dek
from app.db.models import (
    Answer,
    AuditLog,
    ChatMessage,
    Export,
    Structure,
    SurveySession,
    User,
    utcnow,
)
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])
_staff = deps.require_role("admin", "analyst")


def _meta(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.get("/audit/verify")
def verify_audit(
    db: Session = Depends(get_db), _: deps.Principal = Depends(_staff)
) -> Dict[str, Any]:
    return audit.verify_chain(db)


@router.get("/audit")
def recent_audit(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: deps.Principal = Depends(_staff),
) -> List[Dict[str, Any]]:
    rows = db.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(limit)).scalars()
    return [
        {
            "seq": r.seq,
            "ts": deps._aware(r.ts).isoformat(),
            "actor_id": r.actor_id,
            "action": r.action,
            "target": r.target,
            "outcome": r.outcome,
            # Stored as a JSON string; handed back as an object, so a client is
            # not left double-decoding a field inside a JSON response.
            "meta": _meta(r.meta),
            "entry_hash": r.entry_hash[:16],
        }
        for r in rows
    ]


@router.get("/overview")
def overview(
    db: Session = Depends(get_db), _: deps.Principal = Depends(_staff)
) -> Dict[str, Any]:
    answered = dict(
        db.execute(
            select(Answer.session_id, func.count()).group_by(Answer.session_id)
        ).all()
    )
    sessions = []
    for survey in db.execute(select(SurveySession).order_by(SurveySession.started_at.desc())).scalars():
        sessions.append(
            {
                "id": survey.id,
                "structure": survey.structure.name,
                "template_kind": survey.template_kind,
                "status": survey.status,
                "answers": answered.get(survey.id, 0),
                "started_at": deps._aware(survey.started_at).isoformat(),
                "last_activity_at": deps._aware(survey.last_activity_at).isoformat(),
            }
        )
    return {
        "users": db.execute(select(func.count()).select_from(User)).scalar_one(),
        "structures": db.execute(select(func.count()).select_from(Structure)).scalar_one(),
        "exports": db.execute(select(func.count()).select_from(Export)).scalar_one(),
        "sessions": sessions,
    }


# --------------------------------------------------------------------------- #
# Suivi de l'avancement
# --------------------------------------------------------------------------- #
# Only an administrator may reset an interview: it destroys collected answers.
_admin = deps.require_role("admin")


@router.get("/progress")
def progress(
    db: Session = Depends(get_db), _: deps.Principal = Depends(_staff)
) -> Dict[str, Any]:
    """Where every entity stands, whether or not an interview was opened.

    Built from the same `build_state` the interviewee sees, so the percentages
    here and the progress rail can never disagree. Counts and labels only - an
    administrator never sees what was answered.
    """
    from app.api.survey import build_state

    users = {u.id: u for u in db.execute(select(User)).scalars()}
    sessions = list(
        db.execute(select(SurveySession).order_by(SurveySession.last_activity_at.desc())).scalars()
    )
    by_structure = {s.structure_id: s for s in reversed(sessions)}
    # A closed interview outranks an open one for the same entity, exactly as
    # create_session decides which one counts.
    for survey in sessions:
        if survey.status == "completed":
            by_structure[survey.structure_id] = survey

    rows: List[Dict[str, Any]] = []
    for structure in db.execute(select(Structure).order_by(Structure.name)).scalars():
        survey = by_structure.get(structure.id)
        if survey is None:
            rows.append({
                "structure_id": structure.id,
                "structure": structure.name,
                "code": structure.code,
                "template_kind": structure.template_kind,
                "status": "non_demarre",
                "session_id": None,
                "answered": 0,
                "total": 0,
                "percent": 0,
                "missing": [],
                "participant": None,
                "started_at": None,
                "last_activity_at": None,
                "completed_at": None,
            })
            continue

        state = build_state(db, survey)
        participant = users.get(survey.user_id)
        rows.append({
            "structure_id": structure.id,
            "structure": structure.name,
            "code": structure.code,
            "template_kind": survey.template_kind,
            "status": survey.status,
            "session_id": survey.id,
            "answered": state.answered,
            "total": state.total,
            "percent": state.percent,
            "missing": [m.label for m in state.missing],
            "participant": (
                {"name": participant.full_name, "email": participant.email}
                if participant else None
            ),
            "started_at": deps._aware(survey.started_at).isoformat(),
            "last_activity_at": deps._aware(survey.last_activity_at).isoformat(),
            "completed_at": (
                deps._aware(survey.completed_at).isoformat() if survey.completed_at else None
            ),
        })

    started = [r for r in rows if r["status"] != "non_demarre"]
    return {
        "structures": len(rows),
        "not_started": len(rows) - len(started),
        "in_progress": sum(1 for r in started if r["status"] == "in_progress"),
        "completed": sum(1 for r in started if r["status"] == "completed"),
        "points_answered": sum(r["answered"] for r in rows),
        "points_total": sum(r["total"] for r in rows),
        "rows": rows,
    }


@router.post("/sessions/{session_id}/reset")
def reset_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(_admin),
) -> Dict[str, Any]:
    """Put an interview back to its first question.

    Answers and transcript are deleted; the session itself is kept so the audit
    trail and any document already produced still point somewhere real. A closed
    interview reopens, which is what lets an entity be documented again after a
    mistake - the one-interview-per-entity rule reads the same status.

    Deliberately destructive and deliberately narrow: it is the only way to undo
    a wrong entity choice, and it is written to the audit log with the counts it
    destroyed.
    """
    from app.api.survey import append_message
    from app.ai import engine
    from app.pca import transcript
    from app.pca.blueprint import get_plan

    survey = db.get(SurveySession, session_id)
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entretien introuvable.")

    answers = db.execute(
        select(func.count()).select_from(Answer).where(Answer.session_id == survey.id)
    ).scalar_one()
    messages = db.execute(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == survey.id)
    ).scalar_one()

    for row in db.execute(select(Answer).where(Answer.session_id == survey.id)).scalars():
        db.delete(row)
    for row in db.execute(select(ChatMessage).where(ChatMessage.session_id == survey.id)).scalars():
        db.delete(row)
    db.flush()

    was = survey.status
    survey.status = "in_progress"
    survey.completed_at = None
    survey.cursor = 0
    survey.followups = 0
    survey.last_activity_at = utcnow()

    # The interview must open on its greeting, exactly as a new one does.
    dek = unwrap_dek(survey.wrapped_dek)
    plan = get_plan(survey.template_kind)
    append_message(
        db, survey, dek, "assistant",
        engine.greeting(survey.structure.name, len(plan), plan[0].prompt),
        intent="systeme", question_id=plan[0].id,
    )

    audit.record(
        db, action="admin.session_reset", actor_id=principal.id, target=survey.id,
        ip=ratelimit.client_ip(request),
        meta={
            "structure": survey.structure.code,
            "previous_status": was,
            "answers_deleted": answers,
            "messages_deleted": messages,
        },
    )
    db.commit()
    transcript.save(db, survey, dek)

    return {
        "session_id": survey.id,
        "structure": survey.structure.name,
        "previous_status": was,
        "answers_deleted": answers,
        "messages_deleted": messages,
    }
