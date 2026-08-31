"""A readable log of each interview, one file per entity, on the local disk.

The database is the record of truth and keeps every answer encrypted per field.
This is something else: a plain Markdown file an operator can open, read, grep
and archive without the application. It exists because "what exactly did this
person say?" is a question that gets asked long after the interview, and
decrypting the database to answer it is not a workflow.

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

_UNSAFE = re.compile(r"[^A-Za-z0-9]+")

_ROLE = {"user": "Participant", "assistant": "Argus"}


def _slug(text: str) -> str:
    """Filesystem-safe, accent-free, readable at a glance in a file listing."""
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _UNSAFE.sub("_", folded).strip("_")[:70] or "entite"


def filename_for(survey: SurveySession) -> str:
    """`Audit_Comptable_et_Financier_ACF.md` - the entity leads, so the
    directory sorts by the thing an operator is actually looking for."""
    return f"{_slug(survey.structure.name)}_{_slug(survey.structure.code)}.md"


def path_for(survey: SurveySession) -> str:
    return os.path.join(settings.TRANSCRIPT_DIR, filename_for(survey))


def _local(moment: Optional[dt.datetime]) -> str:
    if moment is None:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone().strftime("%d/%m/%Y %H:%M")


def _render_answer(question: Question, payload: Dict[str, Any]) -> List[str]:
    """Grids become Markdown tables; everything else is quoted verbatim."""
    if question.kind == "grid":
        rows = payload.get("rows") or []
        if not rows:
            return ["_(vide)_"]
        # The template's own column headings, not the storage keys: this file is
        # read next to the .docx, and "macro_activite" matches nothing in it.
        keys = [c.id for c in question.columns] or list(rows[0].keys())
        labels = {c.id: c.label for c in question.columns}
        header = "| " + " | ".join(labels.get(k, k) for k in keys) + " |"
        rule = "| " + " | ".join("---" for _ in keys) + " |"
        body = [
            "| " + " | ".join(str(row.get(k, "")).replace("|", r"\|") or " " for k in keys) + " |"
            for row in rows
        ]
        return [header, rule, *body]

    value = (payload.get("value") or "").strip()
    if not value:
        return ["_(vide)_"]
    return [f"> {line}" if line.strip() else ">" for line in value.splitlines()]


def render(db: Session, survey: SurveySession, dek: bytes) -> str:
    """The whole session as Markdown: header, transcript, then the answers."""
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

    out: List[str] = [
        f"# État des lieux — {survey.structure.name}",
        "",
        f"- **Entité** : {survey.structure.name} (`{survey.structure.code}`)",
    ]
    if survey.structure.parent:
        out.append(f"- **Rattachement** : {survey.structure.parent}")
    out += [
        f"- **Modèle** : {'DSI' if survey.template_kind == 'dsi' else 'Entité'}",
        f"- **Participant** : "
        + (f"{participant.full_name} <{participant.email}>" if participant else "—"),
        f"- **Ouvert le** : {_local(survey.started_at)}",
        f"- **Dernière activité** : {_local(survey.last_activity_at)}",
        f"- **Statut** : "
        + ("clôturé le " + _local(survey.completed_at) if survey.status == "completed"
           else "en cours"),
        f"- **Avancement** : {len(filled)} / {len(plan)} points renseignés",
        f"- **Session** : `{survey.id}`",
        "",
        "> Journal généré automatiquement après chaque échange. Le document Word",
        "> reste le livrable ; ce fichier est une trace de lecture.",
        "",
        "---",
        "",
        "## Conversation",
        "",
    ]

    messages = list(
        db.execute(
            select(ChatMessage).where(ChatMessage.session_id == survey.id).order_by(ChatMessage.seq)
        ).scalars()
    )
    if not messages:
        out.append("_Aucun échange._")
    for row in messages:
        body = open_json(dek, survey.id, f"msg:{row.id}", row.body_enc)
        who = _ROLE.get(row.role, row.role)
        stamp = _local(row.created_at)
        tag = f" · _{row.intent}_" if row.intent else ""
        out.append(f"**{who}** — {stamp}{tag}")
        out.append("")
        for line in str(body).splitlines():
            out.append(line)
        out.append("")

    out += ["---", "", "## Réponses enregistrées", ""]
    for index, question in enumerate(plan, start=1):
        row = stored.get(question.id)
        out.append(f"### {index}. {question.label}")
        out.append("")
        out.append(f"_{question.section}_")
        out.append("")
        if row is None:
            out.append("**Sans réponse.**")
        else:
            payload = open_json(dek, survey.id, f"answer:{question.id}", row.payload_enc) or {}
            if not row.confirmed:
                out.append("**Brouillon non confirmé — absent du document.**")
                out.append("")
            out += _render_answer(question, payload)
            out.append("")
            out.append(
                f"<sub>{row.completeness} · révision {row.revision} · "
                f"modifié le {_local(row.updated_at)}</sub>"
            )
        out.append("")

    blank = [q.label for q in plan if q.id not in filled]
    if blank:
        out += ["---", "", f"## Points sans réponse ({len(blank)})", ""]
        out += [f"- {label}" for label in blank]
        out.append("")

    return "\n".join(out)


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
