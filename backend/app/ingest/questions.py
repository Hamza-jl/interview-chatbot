"""Turn a discovered blank into something worth asking a person.

This is the one place a model is used in the ingestion path, and its job is
deliberately small: the slot already knows *what* has to be filled and *where*
it goes. All that is missing is a sentence a human would recognise as a
question, plus a hint and an example.

Keeping it this narrow is what makes a 3-4B model viable. Asked to read a whole
document and invent a questionnaire, a small model hallucinates structure.
Handed one labelled blank and its section, and constrained to a three-field
schema, it does a phrasing job it is actually good at.

Whatever it returns, the label, the columns and the write address come from the
document - never from the model. A bad generation costs an awkward question; it
can never cost a misplaced answer.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .slots import Slot

logger = logging.getLogger("pca.ingest.questions")

# One value per column, never a pre-formatted row.
#
# Asked for "Domaine | Processus | Criticite" as a single string, both candidate
# models got the column count wrong most of the time - 37% correct on qwen2.5:3b,
# 14% on qwen3:4b - and a row with the wrong number of cells is unparseable by
# the deterministic row reader downstream. Asking for a list and joining it here
# makes the structure ours and the wording theirs, which is the right division.
GRID_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "aide": {"type": "string"},
        "valeurs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question", "aide", "valeurs"],
}

CELL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "aide": {"type": "string"},
        "exemple": {"type": "string"},
    },
    "required": ["question", "aide", "exemple"],
}

# Kept for callers that do not branch on the slot kind.
SCHEMA = CELL_SCHEMA


def schema_for(slot: Slot) -> Dict[str, Any]:
    return GRID_SCHEMA if slot.kind == "grid" else CELL_SCHEMA


_ROWISH = re.compile(r"\s*[|/]\s*")


def example_row(slot: Slot, cells: List[str]) -> str:
    """Join model-written cells onto the document's own columns.

    Padded and truncated to the column count, so the result always parses even
    when the model returns the wrong number of values.

    One value per column is what is asked for, but a model will sometimes send
    a list of whole *rows* instead - "Processus 1 / Critique / 24 h" as a single
    value, three times over. Joining those verbatim shows the interviewee three
    example rows where the question asked for one, so a value that is itself a
    complete row is unpacked back into its columns.
    """
    width = len(slot.columns)
    values = [(c or "").strip() for c in cells if (c or "").strip()]

    if width > 1 and values:
        parts = _ROWISH.split(values[0])
        if len(parts) == width:
            values = parts

    values = [v.replace("|", "/") for v in values][:width]
    while len(values) < width:
        values.append(f"<{slot.columns[len(values)]}>")
    return " | ".join(values)

SYSTEM = (
    "Tu prepares un entretien professionnel en francais. On te donne UN champ a "
    "remplir dans un document, avec sa section. Tu rediges la question a poser.\n"
    "\n"
    "REGLES\n"
    "- Une seule question, en francais, vouvoiement, claire et courte.\n"
    "- UN SEUL point d'interrogation. Jamais deux questions collees.\n"
    "- La question n'emploie que les mots du champ, des colonnes et de la section.\n"
    "  Tu n'inventes AUCUN exemple concret dans la question : ni nom de processus,\n"
    "  ni nom d'application, ni chiffre. Les exemples vont uniquement dans\n"
    "  'exemple' ou 'valeurs'.\n"
    "- La personne interrogee ne voit pas le document. La question ne parle JAMAIS\n"
    "  de cellule, de champ, de colonne, de ligne ni de tableau : elle demande\n"
    "  l'information elle-meme.\n"
    "- Tu ne demandes que ce que le champ contient. Tu n'inventes pas de sous-questions.\n"
    "- 'aide' : une phrase qui precise ce qui est attendu.\n"
    "- 'exemple' : une reponse plausible et concrete, pas une consigne.\n"
    "- Pour un tableau : la question demande LA LISTE, une ligne par entree, et\n"
    "  'valeurs' contient UNE SEULE ligne d'exemple : une valeur par colonne, dans\n"
    "  l'ordre exact des colonnes donnees. Autant de valeurs que de colonnes, ni\n"
    "  plus ni moins, et jamais une ligne entiere dans une seule valeur.\n"
    "- Jamais de texte hors du JSON."
)

# A question longer than this has stopped being a question and started being a
# paragraph; the interview shows it as the chatbot's own turn.
_MAX_QUESTION = 220

# A small model loses the thread of a long preamble, and the background is a
# preamble to every one of thirty prompts. Enough for a real briefing, not
# enough to bury the field being asked about.
_MAX_BACKGROUND = 1200

# Keys of the response schema. An answer that is one of these is the model
# repeating the question back, never an example.
_SCHEMA_WORDS = {"valeurs", "cellules", "exemple", "question", "aide", "...", "valeur"}


# Words that describe the document rather than ask for the information. The
# interviewee is in a conversation and has never seen the file, so "la valeur du
# champ 'Site principal'" and "la cellule de la colonne 'Suppleant'" are asking
# them about a spreadsheet they cannot see. Small models produce these by
# echoing the vocabulary of their own instructions.
_PLUMBING = re.compile(
    r"\b(?:cellules?|colonnes?|lignes?|tableaux?|champs?|"
    r"document|formulaire|section)\b",
    re.IGNORECASE,
)


def acceptable(question: str) -> bool:
    """Reject the phrasings that are worse than no model at all.

    Three failures, all observed on qwen2.5:3b against a real questionnaire:
    two questions welded together (which is also how an invented subject
    arrives - "la criticite du processus de gestion des retours d'articles ?",
    a process named nowhere in the document); a question that has grown into a
    paragraph; and a question that describes the file instead of asking for the
    information. The deterministic phrasing beats all three, so the check only
    has to be cheap and certain, not clever.
    """
    text = (question or "").strip()
    if not text or len(text) > _MAX_QUESTION or text.count("?") > 1:
        return False
    return not _PLUMBING.search(text)


@dataclass
class GeneratedQuestion:
    question: str
    help: str
    example: str
    engine: str = ""
    seconds: float = 0.0


def prompt_for(slot: Slot, background: str = "") -> str:
    """The user half of the prompt. Short on purpose - small models drift.

    `background` is what the consultant typed in before the interview. It goes
    first, because it is what makes a generic label specific: "Effectif" asked
    of a four-person team is a different question from "Effectif" asked of a
    directorate, and only the person setting up the interview knows which.
    """
    lines: List[str] = []
    if background:
        lines.append(f"CONTEXTE DE LA MISSION\n{background[:_MAX_BACKGROUND]}\n")
    if slot.context:
        lines.append(f"Section : {' > '.join(slot.context)}")
    lines.append(f"Champ : {slot.label}")
    if slot.kind == "grid":
        lines.append("Type : tableau, plusieurs lignes possibles")
        lines.append("La question demande LA LISTE des entrees, au pluriel.")
        lines.append(f"Colonnes ({len(slot.columns)}) : {' | '.join(slot.columns)}")
    else:
        # Spelled out because a small model otherwise pluralises a single blank
        # ("Quels sont les noms de l'entite ?"), which invites three answers
        # into a box that holds one. Deliberately phrased without the words
        # "cellule" or "champ": it repeats back whatever vocabulary it is given.
        lines.append("Type : UNE SEULE information attendue.")
        lines.append("La question est au SINGULIER et n'appelle qu'une reponse.")
    if slot.existing:
        lines.append(f"Indication presente dans le document : {slot.existing[:200]}")
    lines.append("")
    if slot.kind == "grid":
        lines.append(
            'Reponds en JSON : {"question": "...", "aide": "...", "valeurs": '
            f'[{", ".join(chr(34) + "..." + chr(34) for _ in slot.columns)}]}}'
        )
    else:
        lines.append('Reponds en JSON : {"question": "...", "aide": "...", "exemple": "..."}')
    return "\n".join(lines)


def fallback(slot: Slot) -> GeneratedQuestion:
    """A usable question with no model at all.

    Not a placeholder: if inference is unavailable the interview must still run,
    and a plainly-phrased question beats a broken upload. The same reasoning as
    the deterministic engine on the conversation side.
    """
    if slot.kind == "grid":
        columns = " | ".join(slot.columns)
        return GeneratedQuestion(
            question=(
                f"Pouvez-vous detailler « {slot.label} » ? Une ligne par entree, "
                f"colonnes separees par « | »."
            ),
            help=f"Colonnes attendues, dans l'ordre : {columns}.",
            example=slot.existing or " | ".join(f"<{c}>" for c in slot.columns),
            engine="deterministe",
        )
    return GeneratedQuestion(
        question=f"Quelle est la valeur pour « {slot.label} » ?",
        help=f"Champ « {slot.label} » de la section « {slot.section or 'document'} ».",
        example=slot.existing or "",
        engine="deterministe",
    )


_JSON = re.compile(r"\{.*\}", re.S)


def parse(raw: str) -> Optional[Dict[str, str]]:
    """Read the model's answer, tolerating the wrapping small models add."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        found = _JSON.search(raw)
        if not found:
            return None
        try:
            data = json.loads(found.group(0))
        except ValueError:
            return None
    if not isinstance(data, dict):
        return None
    out: Dict[str, Any] = {
        k: str(data.get(k, "") or "").strip() for k in ("question", "aide", "exemple")
    }
    # "cellules" was the field's first name and models still reach for it, so
    # both are read and only one is handed on.
    cells = data.get("valeurs")
    if not isinstance(cells, list):
        cells = data.get("cellules")
    out["valeurs"] = [str(c) for c in cells] if isinstance(cells, list) else []
    return out if out["question"] else None


def generate(slot: Slot, backend=None, background: str = "") -> GeneratedQuestion:
    """Phrase one question, falling back to a plain one if inference is down.

    Reuses the application's own backend selection, so an upload obeys the same
    LLM_PROVIDER setting as the interview and there is no second place to
    configure a model.
    """
    import time

    from app.ai import llm

    if backend is None:
        backend = llm.active_backend()
    if backend is None:
        return fallback(slot)

    started = time.perf_counter()
    data: Dict[str, Any] = {}
    question = ""

    # Two attempts, then the deterministic phrasing. One retry is worth the
    # seconds because the failures are sporadic rather than systematic - the
    # same slot usually comes back clean - and an unusable question would
    # otherwise be read out to a person.
    for attempt in range(2):
        try:
            data = backend.structured(
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt_for(slot, background)}],
                schema=schema_for(slot),
                max_tokens=400,
            )
        except Exception as exc:                               # noqa: BLE001
            logger.warning("question generation failed for %s: %s", slot.id, exc)
            return fallback(slot)

        question = str(data.get("question") or "").strip()
        if acceptable(question):
            break
        logger.info("rejected phrasing for %s (try %s): %r", slot.id, attempt + 1, question)
        question = ""

    if not question:
        return fallback(slot)

    if slot.kind == "grid":
        cells = data.get("valeurs")
        if not isinstance(cells, list):
            cells = data.get("cellules")
        example = example_row(slot, cells if isinstance(cells, list) else [])
    else:
        example = str(data.get("exemple") or "").strip()
        # Seen in practice: the model echoes a key from the schema instead of
        # writing an example. Shown to the interviewee as "ex. cellules", which
        # is worse than showing nothing.
        if example.lower() in _SCHEMA_WORDS:
            example = ""

    return GeneratedQuestion(
        question=question,
        help=str(data.get("aide") or "").strip(),
        example=example,
        engine=getattr(backend, "label", getattr(backend, "name", "?")),
        seconds=round(time.perf_counter() - started, 1),
    )
