"""Make a discovered document look like a hand-written questionnaire.

`blueprint.PLANS` is a plain dict from a template key to a list of `Question`,
and ten call sites reach it through `get_plan(survey.template_kind)` - the chat
turn, the verification panel, the progress rail, the review gate, the
transcript, the administrator's screen.

Registering a generated plan under its own key, `doc:<id>`, means every one of
those keeps working untouched. An uploaded document becomes an ordinary
interview rather than a parallel implementation of one, which is the difference
between adding a feature and forking the application.

The Target dataclass only addresses Word tables, which is fine - it is what the
Word writer consumes. Non-Word documents keep their real address in the slot and
carry a placeholder Target, because their answers are written by
`write_back`, never by `docx_filler`.
"""
from __future__ import annotations

from typing import Dict, List

from app.pca.blueprint import PLANS, Column, Question, Target

from .slots import DocumentPlan, Slot

PREFIX = "doc:"


def template_kind(document_id: str) -> str:
    return f"{PREFIX}{document_id}"


def is_document(kind: str) -> bool:
    return kind.startswith(PREFIX)


def document_id(kind: str) -> str:
    return kind[len(PREFIX):]


def _column(label: str, index: int) -> Column:
    # The id is what row dictionaries are keyed by end to end - the verification
    # panel, the confirm payload, the writer. The visible label is the only
    # thing a document gives us, so it is both.
    return Column(id=label or f"col{index + 1}", label=label or f"Colonne {index + 1}")


def _target(slot: Slot) -> Target:
    if slot.target.get("table"):
        return Target(
            table=slot.target["table"],
            row=slot.target.get("row"),
            col=slot.target.get("col", 1),
            mode="rows" if slot.kind == "grid" else "cell",
            header_rows=slot.target.get("header_rows", 1),
        )
    # Excel, PowerPoint and PDF are written by write_back from the slot's own
    # address; this exists only to satisfy the dataclass.
    return Target(table=0, mode="rows" if slot.kind == "grid" else "cell")


def to_question(slot: Slot, prompt: str, help_text: str, example: str) -> Question:
    return Question(
        id=slot.id,
        # "field", not "open": a discovered blank is a cell in a table, exactly
        # like a cell of the prepared templates, and the extraction prompt only
        # tells the model to copy an answer verbatim for "field". Called "open",
        # "42 collaborateurs" came back as "nettoye pour 42 collaborateurs" and
        # that is what was written into the client's document.
        kind="grid" if slot.kind == "grid" else "field",
        section=slot.section or "Document",
        label=slot.label,
        prompt=prompt,
        target=_target(slot),
        help=help_text,
        example=example,
        columns=[_column(name, i) for i, name in enumerate(slot.columns)],
        # Nothing discovered in an uploaded file is known to be mandatory, and
        # guessing otherwise would block the review gate on a blank the author
        # never intended to be filled.
        optional=True,
        min_rows=slot.min_rows,
    )


def build(document_id_: str, plan: DocumentPlan, generated: Dict[str, Dict[str, str]]) -> List[Question]:
    """Assemble the questionnaire and register it for `get_plan`."""
    questions: List[Question] = []
    for slot in plan.slots:
        wording = generated.get(slot.id) or {}
        questions.append(
            to_question(
                slot,
                wording.get("question") or f"Quelle est la valeur pour « {slot.label} » ?",
                wording.get("aide", ""),
                wording.get("exemple", ""),
            )
        )
    register(document_id_, questions)
    return questions


def register(document_id_: str, questions: List[Question]) -> str:
    kind = template_kind(document_id_)
    PLANS[kind] = questions
    return kind


def forget(document_id_: str) -> None:
    PLANS.pop(template_kind(document_id_), None)


def is_registered(document_id_: str) -> bool:
    return template_kind(document_id_) in PLANS
