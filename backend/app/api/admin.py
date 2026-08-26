"""Administration surface: audit-chain verification and interview oversight.

Nothing here can read interview content - the endpoints expose counts, states
and integrity proofs only.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import deps
from app.core import audit
from app.db.models import Answer, AuditLog, Export, Structure, SurveySession, User
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])
_staff = deps.require_role("admin", "analyst")


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
            "meta": r.meta,
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
