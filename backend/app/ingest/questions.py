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
        "cellules": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question", "aide", "cellules"],
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


def example_row(slot: Slot, cells: List[str]) -> str:
    """Join model-written cells onto the document's own columns.

    Padded and truncated to the column count, so the result always parses even
    when the model returns the wrong number of values.
    """
    width = len(slot.columns)
    values = [(c or "").strip().replace("|", "/") for c in cells][:width]
    while len(values) < width:
        values.append(f"<{slot.columns[len(values)]}>")
    return " | ".join(values)

SYSTEM = (
    "Tu prepares un entretien professionnel en francais. On te donne UN champ a "
    "remplir dans un document, avec sa section. Tu rediges la question a poser.\n"
    "\n"
    "REGLES\n"
    "- Une seule question, en francais, vouvoiement, claire et courte.\n"
    "- Tu ne demandes que ce que le champ contient. Tu n'inventes pas de sous-questions.\n"
    "- 'aide' : une phrase qui precise ce qui est attendu.\n"
    "- 'exemple' : une reponse plausible et concrete, pas une consigne.\n"
    "- Pour un tableau : la question demande UNE LIGNE PAR ENTREE, et 'cellules'\n"
    "  contient UNE VALEUR PAR COLONNE, dans l'ordre exact des colonnes donnees.\n"
    "  Autant de valeurs que de colonnes, ni plus ni moins.\n"
    "- Jamais de texte hors du JSON."
)


@dataclass
class GeneratedQuestion:
    question: str
    help: str
    example: str
    engine: str = ""
    seconds: float = 0.0


def prompt_for(slot: Slot) -> str:
    """The user half of the prompt. Short on purpose - small models drift."""
    lines: List[str] = []
    if slot.context:
        lines.append(f"Section : {' > '.join(slot.context)}")
    lines.append(f"Champ : {slot.label}")
    if slot.kind == "grid":
        lines.append("Type : tableau, plusieurs lignes possibles")
        lines.append(f"Colonnes ({len(slot.columns)}) : {' | '.join(slot.columns)}")
    else:
        lines.append("Type : reponse unique")
    if slot.existing:
        lines.append(f"Indication presente dans le document : {slot.existing[:200]}")
    lines.append("")
    if slot.kind == "grid":
        lines.append(
            'Reponds en JSON : {"question": "...", "aide": "...", "cellules": '
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
    cells = data.get("cellules")
    out["cellules"] = [str(c) for c in cells] if isinstance(cells, list) else []
    return out if out["question"] else None


def generate(slot: Slot, backend=None) -> GeneratedQuestion:
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
    try:
        data = backend.structured(
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt_for(slot)}],
            schema=schema_for(slot),
            max_tokens=400,
        )
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("question generation failed for %s: %s", slot.id, exc)
        return fallback(slot)

    question = str(data.get("question") or "").strip()
    if not question:
        return fallback(slot)

    if slot.kind == "grid":
        cells = data.get("cellules")
        example = example_row(slot, cells if isinstance(cells, list) else [])
    else:
        example = str(data.get("exemple") or "").strip()

    return GeneratedQuestion(
        question=question,
        help=str(data.get("aide") or "").strip(),
        example=example,
        engine=getattr(backend, "label", getattr(backend, "name", "?")),
        seconds=round(time.perf_counter() - started, 1),
    )
