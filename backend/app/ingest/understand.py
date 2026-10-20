"""Ask a large hosted model what an uploaded file is asking for.

The local 3B model is good at one narrow job: phrasing a question about a blank
somebody else already found. It cannot look at an unfamiliar spreadsheet, a
scanned form or a slide deck and work out what the thing is *for*. That needs a
model with room to reason, which is why this one step - and only this one -
leaves the building.

The division of labour is the same one the rest of the package already rests on,
pushed one level up:

    deterministic readers   decide WHERE an answer can be written
    the hosted model        decides WHICH blanks matter and what to call them
    the local model         phrases the question and reads the reply

For a Word or Excel file the write addresses come from the deterministic reader
and the hosted model only picks and labels - it is never asked to invent a cell
reference, because a hallucinated coordinate puts an answer in the wrong row of
a document somebody signs. For a scan or a photograph there are no addresses to
invent: nothing can be written back, and the model is asked only to describe the
fields so the interview can collect them into a fresh document.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.ai import openrouter
from app.ingest import outbound
from app.ingest.extract import Extraction
from app.ingest.slots import DocumentPlan, Slot

logger = logging.getLogger("pca.ingest.understand")


SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "titre": {"type": "string"},
        "nature": {
            "type": "string",
            "description": "Ce que le document est : questionnaire, fiche, "
                           "tableau de recensement, formulaire, autre.",
        },
        "remplissable": {"type": "boolean"},
        "champs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "L'identifiant exact du champ tel qu'il "
                                       "apparaît dans la liste fournie. Vide si "
                                       "aucune liste n'a été fournie.",
                    },
                    "libelle": {"type": "string"},
                    "section": {"type": "string"},
                    "type": {"type": "string", "enum": ["cellule", "tableau"]},
                    "colonnes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ref", "libelle", "section", "type", "colonnes"],
            },
        },
        "remarques": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["titre", "nature", "remplissable", "champs", "remarques"],
}


SYSTEM = (
    "Tu analyses un document professionnel pour preparer un entretien. "
    "Reponds uniquement en JSON conforme au schema.\n"
    "\n"
    "REGLES\n"
    "- Tu identifies les informations que le document attend : ce qui est vide, "
    "a completer, ou marque par un remplissage provisoire (xx, ..., [a completer], N/A).\n"
    "- Tu ignores ce qui est deja renseigne : on ne redemande pas une reponse "
    "que le document porte deja.\n"
    "- Tu ignores les sommaires, glossaires, mentions legales et pieds de page.\n"
    "- 'ref' : si une liste d'emplacements t'est fournie, recopie l'identifiant "
    "EXACT de la liste. N'invente jamais de reference, ne modifie jamais celles "
    "fournies. Si aucune liste n'est fournie, laisse 'ref' vide.\n"
    "- 'type' vaut 'tableau' quand plusieurs lignes sont attendues, sinon 'cellule'.\n"
    "- 'colonnes' n'est rempli que pour un tableau, avec les en-tetes reels.\n"
    "- 'section' reprend le titre de la partie du document ou se trouve le champ.\n"
    "- Les libelles sont ceux du document, pas une reformulation.\n"
    "- 'remarques' : ce que tu n'as pas pu lire, ou ce qui demandera une reprise "
    "manuelle. Une phrase chacune, en francais."
)


@dataclass
class Understanding:
    plan: DocumentPlan
    model: str
    attempts: List[str]
    seconds: float
    sent: outbound.Outbound
    matched: int = 0          # champs rattachés à un emplacement réel
    invented: int = 0         # refs renvoyées par le modèle qui n'existaient pas


def _prompt(extraction: Extraction, sent: outbound.Outbound) -> str:
    parts: List[str] = [f"FICHIER : {sent.filename} (format {extraction.kind})"]

    if extraction.plan is not None:
        parts.append(
            "\nEMPLACEMENTS REPERES DANS LE FICHIER\n"
            "Choisis parmi ceux-ci. Recopie la reference entre crochets telle quelle."
        )
        for slot in extraction.plan.slots:
            where = " > ".join(slot.context) if slot.context else "-"
            if slot.kind == "grid":
                parts.append(f"  [{slot.id}] TABLEAU · {where} · {slot.label} "
                             f"· colonnes : {' | '.join(slot.columns)}")
            else:
                parts.append(f"  [{slot.id}] CHAMP · {where} · {slot.label}")
    else:
        parts.append(
            "\nAucun emplacement n'a pu etre repere automatiquement : ce format "
            "ne peut pas etre rempli sur place. Laisse 'ref' vide et decris les "
            "informations attendues."
        )

    if sent.text.strip():
        parts.append("\nCONTENU DU FICHIER\n" + sent.text)
    else:
        parts.append("\nLe fichier n'a pas de texte extractible (image ou scan).")

    return "\n".join(parts)


def _to_slots(data: Dict[str, Any], extraction: Extraction) -> tuple[List[Slot], int, int]:
    """Turn the model's answer into slots, keeping real write addresses only."""
    known = {s.id: s for s in (extraction.plan.slots if extraction.plan else [])}
    slots: List[Slot] = []
    matched = invented = 0

    for index, field in enumerate(data.get("champs") or []):
        ref = (field.get("ref") or "").strip().strip("[]")
        label = (field.get("libelle") or "").strip()
        if not label:
            continue
        section = (field.get("section") or "").strip()
        is_grid = (field.get("type") or "") == "tableau"
        columns = [c for c in (field.get("colonnes") or []) if str(c).strip()]

        if ref and ref in known:
            # The model picked a real location: keep the deterministic target
            # and the deterministic column set, take only its wording.
            base = known[ref]
            matched += 1
            slots.append(Slot(
                id=base.id, kind=base.kind, label=label or base.label,
                target=base.target, context=base.context or ([section] if section else []),
                # Columns belong to the table, so they come from the reader. A
                # single cell has none: models offer its own label back as a
                # column, which would turn one blank into a one-column grid.
                columns=base.columns if base.kind == "grid" else [],
                existing=base.existing, min_rows=base.min_rows,
            ))
            continue

        if ref:
            # A reference that does not exist. Not fatal, but it means the model
            # is guessing, and a guessed address must never reach write-back.
            invented += 1
            logger.warning("understand: référence inconnue %r ignorée", ref)

        # No usable address: collectable, not writable in place.
        slots.append(Slot(
            id=f"cloud.{index}", kind="grid" if is_grid else "cell",
            label=label, target={}, context=[section] if section else [],
            columns=columns,
        ))

    return slots, matched, invented


def understand(extraction: Extraction, filename: str,
               answers: Optional[List[str]] = None) -> Understanding:
    """Send one file out, get back a plan. Raises if the chain is exhausted."""
    sent = outbound.prepare(
        filename=filename, kind=extraction.kind, text=extraction.text,
        answers=answers, images=extraction.images,
    )

    result = openrouter.structured(
        system=SYSTEM, user=_prompt(extraction, sent), schema=SCHEMA,
    )
    data = result.data

    slots, matched, invented = _to_slots(data, extraction)
    notes = list(extraction.notes)
    notes += [str(r) for r in (data.get("remarques") or []) if str(r).strip()]
    if invented:
        notes.append(
            f"{invented} emplacement(s) proposé(s) par le modèle n'ont pas été "
            "retrouvés dans le fichier : ces réponses seront collectées mais non "
            "écrites automatiquement."
        )

    plan = DocumentPlan(
        filename=filename,
        kind=extraction.kind,
        title=(data.get("titre") or "").strip() or filename,
        slots=slots,
        notes=notes,
    )

    logger.info("understand: %s -> %d champ(s) (%d rattachés) via %s en %ss",
                filename, len(slots), matched, result.model, result.seconds)

    return Understanding(plan=plan, model=result.model, attempts=result.attempts,
                         seconds=result.seconds, sent=sent,
                         matched=matched, invented=invented)
