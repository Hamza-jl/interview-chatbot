"""Tamper-evident audit trail.

Each entry commits to the digest of the previous one, so removing or editing a
past event invalidates every subsequent hash.  ``verify_chain`` recomputes the
whole chain and reports the first break.

Audit metadata deliberately never carries interview content - only identifiers,
question ids and counts.
"""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.core.security import pseudonymize

GENESIS = "0" * 64
_lock = threading.Lock()

# Fields that must never reach the audit table even if a caller passes them.
_FORBIDDEN = {"value", "rows", "answer", "message", "body", "password", "totp", "content"}


def _digest(entry: Dict[str, Any]) -> str:
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _scrub(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {k: v for k, v in (meta or {}).items() if k.lower() not in _FORBIDDEN}


def record(
    db: Session,
    *,
    action: str,
    actor_id: Optional[str] = None,
    target: str = "",
    outcome: str = "ok",
    ip: str = "",
    user_agent: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Append one event. Callers must still commit the surrounding transaction."""
    with _lock:
        prev = db.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar_one_or_none()
        prev_hash = prev.entry_hash if prev else GENESIS

        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target=target[:120],
            outcome=outcome,
            ip_fp=pseudonymize(ip) if ip else "",
            ua_fp=pseudonymize(user_agent) if user_agent else "",
            meta=json.dumps(_scrub(meta), sort_keys=True, ensure_ascii=False),
            prev_hash=prev_hash,
        )
        entry.entry_hash = _digest(
            {
                "actor": entry.actor_id,
                "action": entry.action,
                "target": entry.target,
                "outcome": entry.outcome,
                "ip": entry.ip_fp,
                "ua": entry.ua_fp,
                "meta": entry.meta,
                "prev": prev_hash,
            }
        )
        db.add(entry)
        db.flush()
        return entry


def verify_chain(db: Session) -> Dict[str, Any]:
    """Recompute the chain. Returns the first broken sequence number, if any."""
    prev_hash = GENESIS
    count = 0
    for entry in db.execute(select(AuditLog).order_by(AuditLog.seq.asc())).scalars():
        expected = _digest(
            {
                "actor": entry.actor_id,
                "action": entry.action,
                "target": entry.target,
                "outcome": entry.outcome,
                "ip": entry.ip_fp,
                "ua": entry.ua_fp,
                "meta": entry.meta,
                "prev": prev_hash,
            }
        )
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            return {"valid": False, "entries": count, "broken_at": entry.seq}
        prev_hash = entry.entry_hash
        count += 1
    return {"valid": True, "entries": count, "broken_at": None}
