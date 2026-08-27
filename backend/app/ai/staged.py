"""Staged pipeline for small local models.

A 3B model cannot fill the eight-field turn schema in one pass: constrained
decoding forces it to commit to `intent` before it has generated any text, and
it collapses to one label with empty fields. Measured on qwen2.5:3b, the single
call answered "question" to every message.

Split into single-purpose calls it is reliable and *faster*, because each call
emits far fewer tokens:

    1. classify   - one enum field, few-shot          (~2.7 s, 6/6 on the probe set)
    2a. question  - no model call: the glossary entry is served verbatim
    2b. answer    - one `value` field  (open/field)   (~3 s)
    2c. answer    - `rows[]`           (grid)         (~4 s)

Serving definitions verbatim rather than paraphrasing them is a deliberate
choice: in an audit tool the authoritative wording of the client's own template
matters more than conversational polish, and it removes any chance of a small
model inventing a definition.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.ai import social
from app.ai.llm import LLMUnavailable
from app.pca import glossary
from app.pca.blueprint import Question

logger = logging.getLogger("pca.staged")


# --------------------------------------------------------------------------- #
# Stage 1 - intent
# --------------------------------------------------------------------------- #
CLASSIFY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["reponse", "question", "navigation", "hors_sujet", "salutation"],
        }
    },
    "required": ["intent"],
}

CLASSIFY_SYSTEM = """Tu classes le message d'un interlocuteur pendant un entretien professionnel.

- "question" : il demande une explication, une définition, un exemple, ou dit qu'il
  ne comprend pas. Souvent un "?", "qu'est-ce que", "c'est quoi", "que signifie".
- "navigation" : il veut passer, revenir en arriere, repeter ou arreter. Souvent
  "je ne sais pas", "je n'ai pas cette information", "passons", "suivant".
- "reponse" : il donne une information factuelle qui repond à la question posee.
- "hors_sujet" : le message n'a aucun rapport avec l'entretien.
- "salutation" : UNIQUEMENT une formule de politesse isolee, qui ne contient
  aucune information - « bonjour », « merci », « d'accord ». Un nom de personne,
  même seul et sans verbe, est une "reponse", jamais une salutation.

Exemples :
Message: "42 collaborateurs dans 4 pôles." -> reponse
Message: "Qu'est-ce que la criticité SI ?" -> question
Message: "Je ne dispose pas de cette information." -> navigation
Message: "Comité SI mensuel preside par le DGA." -> reponse
Message: "Pouvez-vous me donner un exemple ?" -> question
Message: "Delta Crédit, vital, contournement papier." -> reponse
Message: "quel temps fait-il aujourd'hui" -> hors_sujet
Message: "bonjour" -> salutation
Message: "merci beaucoup" -> salutation
Message: "d'accord" -> salutation
Message: "Mme Sonia Ben Ammar" -> reponse
Message: "M. Karim Trabelsi, Responsable Production" -> reponse
Message: "Mme Ines Gharbi" -> reponse
Message: "Direction des Engagements" -> reponse

Renvoie uniquement le champ intent."""


def classify(backend, message: str, question: Question) -> str:
    result = backend.structured(
        system=CLASSIFY_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f'QUESTION POSEE : {question.prompt}\n'
                    f'Message: "{message}"'
                ),
            }
        ],
        schema=CLASSIFY_SCHEMA,
        max_tokens=32,
    )
    intent = result.get("intent")
    valid = {"reponse", "question", "navigation", "hors_sujet", "salutation"}
    return intent if intent in valid else "reponse"


# --------------------------------------------------------------------------- #
# Stage 2b - rewrite a free-text answer
# --------------------------------------------------------------------------- #
VALUE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
}

REWRITE_SYSTEM = """Tu reformules la réponse d'un interlocuteur pour un rapport d'audit.

RÈGLE ABSOLUE : reste strictement fidele au message. N'ajoute aucun chiffre,
aucun nom, aucune information qui ne soit pas dans le message. Si le message est
vague, reste vague.

Ecris une à trois phrases sobres en francais, a la troisieme personne, sans
formule de politesse. Renvoie uniquement le champ value."""


def rewrite(backend, message: str, question: Question, existing: Optional[str]) -> str:
    prompt = f"QUESTION : {question.prompt}\n"
    if existing:
        prompt += f"DEJA CONSIGNE : {existing}\n(complete ce texte avec le nouveau message)\n"
    prompt += f"MESSAGE : {message}"

    result = backend.structured(
        system=REWRITE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        schema=VALUE_SCHEMA,
        max_tokens=500,
    )
    return str(result.get("value") or "").strip()


# --------------------------------------------------------------------------- #
# Stage 2b-bis - short identity fields (fiche de suivi)
# --------------------------------------------------------------------------- #
FIELD_SYSTEM = """Tu extrais UNE valeur courte depuis le message d'un interlocuteur.

La valeur alimente une cellule de fiche de suivi : un nom, une fonction, une date.
- Renvoie uniquement la valeur, sans phrase, sans verbe, sans article introductif.
- Retire les formules du type « c'est », « il s'agit de », « le responsable est ».
- Conserve les titres (M., Mme) et les fonctions PRÉSENTS dans le message.
- N'ajoute jamais un titre absent : « Karim Trabelsi » reste « Karim Trabelsi ».
- N'invente rien. Si le message ne contient pas de valeur, renvoie une chaine vide.

Exemples :
Message: "c'est Mme Sonia Ben Ammar qui dirige l'entité" -> "Mme Sonia Ben Ammar"
Message: "le responsable est M. Karim Trabelsi, chef de production"
  -> "M. Karim Trabelsi, chef de production"
Message: "Mme Ines Gharbi" -> "Mme Ines Gharbi"
Message: "Karim Trabelsi" -> "Karim Trabelsi"

Renvoie uniquement le champ value."""


def extract_field(backend, message: str, question: Question) -> str:
    """Pull the bare value out of a conversational sentence."""
    result = backend.structured(
        system=FIELD_SYSTEM,
        messages=[
            {"role": "user", "content": f"CHAMP : {question.label}\nMESSAGE : {message}"}
        ],
        schema=VALUE_SCHEMA,
        max_tokens=120,
    )
    value = str(result.get("value") or "").strip().strip('"')
    # Never let a rewrite balloon into prose: fall back to what was typed.
    return value if value and len(value) <= max(80, len(message)) else message.strip()


# --------------------------------------------------------------------------- #
# Stage 2c - extract table rows
# --------------------------------------------------------------------------- #
def rows_schema(question: Question) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    for column in question.columns:
        if column.choices:
            properties[column.id] = {"type": "string", "enum": [*column.choices, ""]}
        else:
            properties[column.id] = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": [c.id for c in question.columns],
                },
            }
        },
        "required": ["rows"],
    }


def _columns_doc(question: Question) -> str:
    lines = []
    for column in question.columns:
        bits = [f"- {column.id} : {column.label}"]
        if column.hint:
            bits.append(f" ({column.hint})")
        if column.choices:
            bits.append(f" [valeurs autorisees : {', '.join(column.choices)}]")
        lines.append("".join(bits))
    return "\n".join(lines)


EXTRACT_SYSTEM = """Tu extrais des lignes de tableau depuis le message d'un interlocuteur.

RÈGLES
- Une ligne par élément concret cite dans le message.
- Remplis CHAQUE colonne, en commencant par la première. Ne decale jamais les
  valeurs d'une colonne vers la suivante.
- N'invente rien. Si une colonne n'est pas précisée, mets une chaine vide.
- Si le message utilisé le caractère « | », chaque ligne du message est une ligne
  du tableau et chaque segment correspond à une colonne, dans l'ordre.

Renvoie uniquement le champ rows."""


def _example_row(question: Question) -> str:
    """Turn the blueprint's pipe-separated example into a worked JSON example.

    A small model given only a pipe string infers the column mapping itself and
    gets it wrong - measured on qwen2.5:3b, every value landed one column to the
    right and the first column came back empty. Showing the mapping explicitly
    fixes it.
    """
    segments = [s.strip() for s in (question.example or "").split("|")]
    if len(segments) != len(question.columns):
        return ""
    example = {c.id: segments[i] for i, c in enumerate(question.columns)}
    return (
        "EXEMPLE\n"
        f'Message: "{question.example}"\n'
        f'-> rows: [{json.dumps(example, ensure_ascii=False)}]'
    )


def parse_pipe_rows(message: str, question: Question) -> List[Dict[str, str]]:
    """Map ``a | b | c`` lines straight onto the columns, without a model.

    The guided grid in the UI emits exactly this shape, column by column, so the
    mapping is already known. Sending it to a model can only degrade it: on
    qwen2.5:3b the same input produced different column assignments across runs
    even at temperature 0. Returns [] when the message is not in this form.
    """
    lines = [ln for ln in (message or "").splitlines() if ln.strip()]
    if not lines or not all("|" in ln for ln in lines):
        return []

    rows: List[Dict[str, str]] = []
    for line in lines:
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > len(question.columns):
            return []  # ambiguous - let the model decide instead
        row = {c.id: (cells[i] if i < len(cells) else "") for i, c in enumerate(question.columns)}
        if any(row.values()):
            rows.append(row)
    return rows


def extract_rows(
    backend, message: str, question: Question, existing: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    direct = parse_pipe_rows(message, question)
    if direct:
        return _merge(existing, direct)

    prompt = (
        f"QUESTION : {question.prompt}\n\n"
        f"COLONNES (dans l'ordre)\n{_columns_doc(question)}\n\n"
    )
    example = _example_row(question)
    if example:
        prompt += f"{example}\n\n"
    prompt += f"Message:\n{message}"

    result = backend.structured(
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        schema=rows_schema(question),
        max_tokens=900,
    )

    allowed = {c.id for c in question.columns}
    fresh: List[Dict[str, str]] = []
    for row in result.get("rows") or []:
        if not isinstance(row, dict):
            continue
        clean = {k: str(v or "").strip() for k, v in row.items() if k in allowed}
        if any(clean.values()):
            fresh.append({c.id: clean.get(c.id, "") for c in question.columns})

    return _merge(existing, fresh)


def _merge(existing: List[Dict[str, str]], fresh: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Rows accumulate across turns: a table may be filled in progressively."""
    merged = list(existing)
    seen = {tuple(sorted(r.items())) for r in merged}
    for row in fresh:
        key = tuple(sorted(row.items()))
        if key not in seen:
            merged.append(row)
            seen.add(key)
    return merged


# --------------------------------------------------------------------------- #
# Definitions - served verbatim, never paraphrased
# --------------------------------------------------------------------------- #
def answer_definition(message: str, question: Question) -> str:
    # "Un exemple ?" is not a glossary lookup. Searching the referential for it
    # used to return whichever entry shared a word - in one interview a request
    # for an example of activity mapping came back with "Periodes critiques".
    if social.wants_example(message):
        parts = [f"Voici le format attendu pour cette question :\n\n> {question.example}"]
        if question.columns:
            parts.append(
                "Colonnes, dans l'ordre : "
                + " | ".join(c.label for c in question.columns)
                + "\n\nVous pouvez aussi utiliser la saisie guidee, qui remplit "
                "chaque colonne separement."
            )
        if question.help:
            parts.append(question.help)
        parts.append(f"Pour revenir à notre point : {question.prompt}")
        return "\n\n".join(parts)

    hits = glossary.search(message, limit=2)
    if hits:
        body = "\n\n".join(f"**{entry.term}**\n{entry.definition}" for entry in hits)
        return f"{body}\n\nPour revenir a notre point : {question.prompt}"
    return (
        "Ce terme ne figure pas dans le référentiel de l'atelier. Je note votre question "
        "pour le consultant Devoteam, qui vous repondra precisement.\n\n"
        f"Pour revenir à notre point : {question.prompt}"
    )
