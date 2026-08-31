"""The conversational endpoint - one user message, one orchestrated turn."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import engine
from app.api import deps
from app.api.survey import (
    append_message,
    build_state,
    end_of_plan,
    pending_answer,
    read_answer,
    store_answer,
)
from app.core import audit, ratelimit
from app.core.config import settings
from app.core.crypto import open_json, unwrap_dek
from app.db.models import Answer, ChatMessage, SurveySession, utcnow
from app.db.session import get_db
from app.pca import transcript
from app.pca.blueprint import get_plan
from app.schemas.api import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])

HISTORY_TURNS = 8

VERIFY_PROMPT = (
    "Vérifiez ce que j'ai retenu dans le panneau de droite, corrigez si "
    "nécessaire, puis confirmez pour passer à la suite."
)


def _history(db: Session, survey: SurveySession, dek: bytes) -> List[Dict[str, str]]:
    rows = list(
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == survey.id)
            .order_by(ChatMessage.seq.desc())
            .limit(HISTORY_TURNS)
        ).scalars()
    )
    rows.reverse()
    return [
        {"role": r.role, "body": open_json(dek, survey.id, f"msg:{r.id}", r.body_enc)}
        for r in rows
    ]


def _existing_payload(db: Session, survey: SurveySession, dek: bytes, question_id: str):
    row = db.execute(
        select(Answer).where(Answer.session_id == survey.id, Answer.question_id == question_id)
    ).scalar_one_or_none()
    return read_answer(dek, survey.id, row)


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def send_message(
    session_id: str,
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> ChatResponse:
    ratelimit.enforce(request, "chat", settings.RL_CHAT, subject=principal.id)

    survey = deps.load_active_session(db, principal.id, session_id)
    if survey.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet entretien est clôturé. Vous pouvez télécharger le document produit.",
        )

    plan = get_plan(survey.template_kind)
    total = len(plan)
    # Past the last question the session is awaiting its final review. Clamping
    # the cursor back here would file the message against a question that has
    # already been confirmed - the interviewee picks a blank point or closes.
    if survey.cursor >= total:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Toutes les questions ont été parcourues. Sélectionnez un point "
                "à compléter, ou clôturez l'entretien."
            ),
        )

    dek = unwrap_dek(survey.wrapped_dek)
    cursor = max(0, min(survey.cursor, total - 1))
    question = plan[cursor]

    append_message(db, survey, dek, "user", payload.message, question_id=question.id)

    result = engine.run_turn(
        question,
        payload.message,
        _history(db, survey, dek),
        structure_name=survey.structure.name,
        template_label=survey.template_kind,
        position=f"question {cursor + 1} sur {total}",
        existing=_existing_payload(db, survey, dek, question.id),
        followups=survey.followups,
        total=total,
    )

    recorded = False
    pending = None
    if result.has_data and result.intent in {"reponse", "mixte"}:
        completeness = "complete" if result.completeness == "complete" else "partielle"
        # Stored as a DRAFT. The interview holds here until the interviewee has
        # seen the extraction laid out and confirmed it, so nothing the engine
        # inferred can reach the client's document unreviewed.
        store_answer(db, survey, dek, question, result.data, completeness)
        recorded = True
        pending = pending_answer(question, result.data)

    if pending is not None:
        # Do not advance and do not append a next question: the turn is not over
        # until it is confirmed.
        survey.followups = 0
        survey.last_activity_at = utcnow()
        reply_row = append_message(
            db, survey, dek, "assistant",
            f"{result.reply}\n\n{VERIFY_PROMPT}",
            intent=result.intent, question_id=question.id,
        )
        audit.record(
            db, action="survey.draft", actor_id=principal.id, target=survey.id,
            ip=ratelimit.client_ip(request),
            meta={"question_id": question.id, "intent": result.intent,
                  "completeness": result.completeness, "engine": result.engine},
        )
        db.commit()
        transcript.save(db, survey, dek)
        db.refresh(reply_row)

        from app.api.survey import _message_out

        return ChatResponse(
            reply=_message_out(dek, survey.id, reply_row),
            state=build_state(db, survey, degraded=result.degraded, engine_label=result.engine),
            intent=result.intent,
            recorded=False,          # not recorded until confirmed
            completed=False,
            pending=pending,
        )

    cursor = _move_cursor(survey, result, cursor, total)

    completed = False
    reply_text = result.reply
    if cursor >= total:
        tail, completed = end_of_plan(db, survey)
        reply_text = f"{result.reply}\n\n{tail}"
    else:
        next_question = plan[cursor]
        if result.advance or result.nav in {"suivant", "precedent"}:
            reply_text = f"{result.reply}\n\n{next_question.prompt}"

    survey.last_activity_at = utcnow()
    reply_row = append_message(
        db, survey, dek, "assistant", reply_text, intent=result.intent,
        question_id=plan[cursor].id if cursor < total else None,
    )

    audit.record(
        db,
        action="survey.turn",
        actor_id=principal.id,
        target=survey.id,
        ip=ratelimit.client_ip(request),
        meta={
            "question_id": question.id,
            "intent": result.intent,
            "recorded": recorded,
            "completeness": result.completeness,
            "degraded": result.degraded,
            # Which engine produced this extraction - an auditor must be able to
            # establish that after the fact.
            "engine": result.engine,
        },
    )
    db.commit()
    transcript.save(db, survey, dek)
    db.refresh(reply_row)

    from app.api.survey import _message_out

    return ChatResponse(
        reply=_message_out(dek, survey.id, reply_row),
        state=build_state(db, survey, degraded=result.degraded, engine_label=result.engine),
        intent=result.intent,
        recorded=recorded,
        completed=completed,
    )


# Turns that are not attempts at answering, and so never burn a follow-up. The
# allowance exists for the case it was built for: an answer the engine could not
# get anything usable out of (intent "reponse", no data). Off-topic belongs here
# too - it is by definition not an answer.
_CONVERSATIONAL = {"salutation", "question", "navigation", "hors_sujet"}


def _move_cursor(
    survey: SurveySession, result: engine.TurnResult, cursor: int, total: int
) -> int:
    """Advance, rewind or hold. Returns the new cursor and syncs the session."""
    if result.nav == "terminer":
        survey.cursor = total
        survey.followups = 0
        return total
    if result.nav == "precedent":
        cursor = max(0, cursor - 1)
    elif result.advance or result.nav == "suivant":
        cursor += 1
    elif result.intent in _CONVERSATIONAL:
        # Courtesy, a definition request or a question about the workshop holds
        # the interview where it is, free of charge. The follow-up allowance is
        # there for answers the engine could not use - spending it on ordinary
        # conversation advanced the interview past a question nobody had
        # answered: four such turns in a row were enough to skip question 1.
        survey.cursor = cursor
        return cursor
    else:
        # Held on the same question: count the relance so we never loop forever.
        survey.followups += 1
        if survey.followups > engine.MAX_FOLLOWUPS:
            cursor += 1
        else:
            survey.cursor = cursor
            return cursor

    survey.followups = 0
    survey.cursor = min(cursor, total)
    return survey.cursor
