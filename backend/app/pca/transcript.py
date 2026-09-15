"""A machine-readable log of each interview, one file per entity, on local disk.

The database is the record of truth and keeps every answer encrypted per field.
This is something else: a plain JSON file an operator can open, parse and feed to
another tool without the application. It exists because "what exactly did this
person say?" is a question that gets asked long after the interview, and
decrypting the database to answer it is not a workflow.

JSON rather than prose: these files are meant to be reused - loaded into a
notebook, diffed, aggregated across entities - so the structure is stable and
the timestamps are ISO 8601 UTC rather than something pleasant to read.

Two consequences follow, and both are deliberate:

* the file is PLAINTEXT. Everything the per-field encryption protects is legible
  to anyone who can read the directory. That is why this is off unless
  ``TRANSCRIPT_ENABLED`` is set, and why the directory belongs somewhere the
  operating system protects.
* it is rewritten in full after every turn rather than appended to. Appending
  drifts from the database the first time an answer is corrected from the rail;
  a full rewrite is always exactly what the session currently holds, and an
  interview is far too small for the cost to matter.

A failure here must never break an interview: the caller's work is already
committed by the time we run, so every error is logged and swallowed.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import open_json
from app.db.models import Answer, ChatMessage, SurveySession, User
from app.pca.blueprint import Question, get_plan

logger = logging.getLogger("pca.transcript")

# Bumped when the shape below changes in a way a consumer would notice, so a
# script that reads these files can refuse a version it does not understand.
SCHEMA = "etat-des-lieux/interview"
SCHEMA_VERSION = 1

_UNSAFE = re.compile(r"[^A-Za-z0-9]+")

_ROLE = {"user": "Participant", "assistant": "Argus"}


def _slug(text: str) -> str:
    """Filesystem-safe, accent-free, readable at a glance in a file listing."""
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _UNSAFE.sub("_", folded).strip("_")[:70] or "entite"


def filename_for(survey: SurveySession) -> str:
    """`Audit_Comptable_et_Financier_ACF_1b1554d6.json`.

    The entity leads, so the directory sorts by the thing an operator is
    actually looking for. The session id follows because an entity holds more
    than one interview more often than it looks - a correspondent changes, an
    account is retired and its sessions stay behind - and keying on the entity
    alone lets a later interview silently overwrite a finished one.
    """
    return (
        f"{_slug(survey.structure.name)}_{_slug(survey.structure.code)}"
        f"_{str(survey.id)[:8]}.json"
    )


def path_for(survey: SurveySession) -> str:
    return os.path.join(settings.TRANSCRIPT_DIR, filename_for(survey))


def _iso(moment: Optional[dt.datetime]) -> Optional[str]:
    """ISO 8601 in UTC, or null. Naive values are stored UTC, so say so."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).isoformat()


def _answer_payload(question: Question, payload: Dict[str, Any]) -> Dict[str, Any]:
    """The stored answer, shaped by question kind.

    Grids keep their raw row dicts - the storage keys are what a consumer joins
    on - and carry the column definitions alongside, so a reader can label them
    without loading the questionnaire blueprint.
    """
    if question.kind == "grid":
        return {
            "columns": [{"id": c.id, "label": c.label} for c in question.columns],
            "rows": payload.get("rows") or [],
        }
    return {"value": (payload.get("value") or "").strip() or None}


def build(db: Session, survey: SurveySession, dek: bytes) -> Dict[str, Any]:
    """The whole session as a plain dict: header, conversation, then answers."""
    plan = get_plan(survey.template_kind)
    stored = {
        a.question_id: a
        for a in db.execute(select(Answer).where(Answer.session_id == survey.id)).scalars()
    }
    filled = {
        q.id for q in plan
        if (a := stored.get(q.id)) and a.confirmed and a.completeness != "vide"
    }
    participant = db.get(User, survey.user_id)

    messages = list(
        db.execute(
            select(ChatMessage).where(ChatMessage.session_id == survey.id).order_by(ChatMessage.seq)
        ).scalars()
    )

    conversation: List[Dict[str, Any]] = []
    for row in messages:
        body = open_json(dek, survey.id, f"msg:{row.id}", row.body_enc)
        conversation.append({
            "seq": row.seq,
            "role": row.role,
            "speaker": _ROLE.get(row.role, row.role),
            "at": _iso(row.created_at),
            "intent": row.intent or None,
            "text": str(body),
        })

    answers: List[Dict[str, Any]] = []
    for index, question in enumerate(plan, start=1):
        row = stored.get(question.id)
        entry: Dict[str, Any] = {
            "index": index,
            "question_id": question.id,
            "section": question.section,
            "label": question.label,
            "kind": question.kind,
            "answered": row is not None,
        }
        if row is None:
            entry.update({
                "confirmed": False,
                "completeness": None,
                "revision": None,
                "updated_at": None,
                "answer": None,
            })
        else:
            payload = open_json(dek, survey.id, f"answer:{question.id}", row.payload_enc) or {}
            entry.update({
                # An unconfirmed draft is absent from the Word document. It is
                # kept here, flagged, because it is still what the person typed.
                "confirmed": bool(row.confirmed),
                "completeness": row.completeness,
                "revision": row.revision,
                "updated_at": _iso(row.updated_at),
                "answer": _answer_payload(question, payload),
            })
        answers.append(entry)

    return {
        "schema": SCHEMA,
        "version": SCHEMA_VERSION,
        "generated_at": _iso(dt.datetime.now(dt.timezone.utc)),
        "session": {
            "id": survey.id,
            "status": survey.status,
            "template_kind": survey.template_kind,
            "started_at": _iso(survey.started_at),
            "last_activity_at": _iso(survey.last_activity_at),
            "completed_at": _iso(survey.completed_at),
        },
        "entity": {
            "code": survey.structure.code,
            "name": survey.structure.name,
            "parent": survey.structure.parent or None,
        },
        "participant": (
            {"full_name": participant.full_name, "email": participant.email}
            if participant else None
        ),
        "progress": {"answered": len(filled), "total": len(plan)},
        "conversation": conversation,
        "answers": answers,
        "unanswered": [
            {"question_id": q.id, "label": q.label} for q in plan if q.id not in filled
        ],
    }


def render(db: Session, survey: SurveySession, dek: bytes) -> str:
    """The session as a JSON document, ready to write."""
    return json.dumps(build(db, survey, dek), ensure_ascii=False, indent=2) + "\n"


def save(db: Session, survey: SurveySession, dek: bytes) -> Optional[str]:
    """Write the log for this session. Returns the path, or None if disabled.

    Never raises: the interview it belongs to is already committed, and losing a
    convenience file is not a reason to fail the request that produced it.
    """
    if not settings.TRANSCRIPT_ENABLED:
        return None
    try:
        os.makedirs(settings.TRANSCRIPT_DIR, exist_ok=True)
        target = path_for(survey)
        # Written beside the target and moved into place, so a reader never
        # catches a half-written file - these are rewritten on every turn.
        staging = f"{target}.tmp"
        with open(staging, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render(db, survey, dek))
        os.replace(staging, target)
        return target
    except Exception:                                   # noqa: BLE001 - see docstring
        logger.exception("could not write the transcript for session %s", survey.id)
        return None
