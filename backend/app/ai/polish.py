"""Rewrite recorded answers into clean prose, for the document only.

The database keeps what the correspondent actually said, word for word. This
runs over a *copy* on its way into the .docx, and that separation is the whole
design: "embellir" must never become a silent edit of someone's testimony.
Skip it, re-run it, or download the plain version - the stored answer is
identical either way, and so is the transcript and the audit trail.

Tables are left alone on purpose. A grid cell holds a system name, a process or
a criticality letter; there is no prose to improve, and a model asked to
improve one invents a better-sounding system that does not exist.

Inference is local and runs on the CPU here, so this is slow by nature - one
call per written answer. It is a button somebody presses deliberately, never
something that happens on the way past.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.ai import llm
from app.pca.blueprint import Question

logger = logging.getLogger("pca.polish")

# Constrained decoding: the reply always parses, so a chatty model cannot
# wrap the rewrite in "Voici la version amelioree :".
_SCHEMA = {
    "type": "object",
    "properties": {"texte": {"type": "string"}},
    "required": ["texte"],
}

_SYSTEM = (
    "Tu ameliores la FORME d'une reponse d'entretien professionnel, en francais.\n"
    "\n"
    "Regles absolues :\n"
    "- n'ajoute AUCUN fait, chiffre, nom, delai ou systeme absent du texte ;\n"
    "- ne supprime aucune information, meme secondaire ;\n"
    "- n'invente pas de precision : si le texte est vague, il reste vague ;\n"
    "- corrige l'orthographe, la ponctuation, les accents et la syntaxe ;\n"
    "- adopte un ton neutre et professionnel, a la troisieme personne ;\n"
    "- garde la longueur d'origine, a peu pres ;\n"
    "- reponds uniquement avec le texte reformule, dans le champ « texte »."
)

# A one-word answer ("Oui", "Aucun", a name) has no prose to improve, and a
# model handed one writes a paragraph around it.
_MIN_CHARS = 25


def _rewrite(backend: Any, label: str, value: str) -> str | None:
    result = backend.structured(
        system=_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Rubrique : {label}\n\nReponse a reformuler :\n{value}",
        }],
        schema=_SCHEMA,
        max_tokens=700,
    )
    better = (result or {}).get("texte")
    return better.strip() if isinstance(better, str) and better.strip() else None


def polish_answers(
    answers: Dict[str, Dict[str, Any]], plan: List[Question]
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """Return a polished copy of `answers`, and how many were rewritten.

    Never raises and never returns fewer answers than it was given: a document
    that loses a section because the model stumbled is far worse than one whose
    prose was left as typed. Each failure keeps the original and moves on.
    """
    backend = llm.active_backend()
    if backend is None:
        logger.info("no inference backend available; answers left as recorded")
        return dict(answers), 0

    labels = {q.id: q.label for q in plan}
    kinds = {q.id: q.kind for q in plan}

    out: Dict[str, Dict[str, Any]] = {}
    rewritten = 0
    for question_id, payload in answers.items():
        out[question_id] = payload
        if kinds.get(question_id) == "grid":
            continue

        value = str((payload or {}).get("value") or "").strip()
        if len(value) < _MIN_CHARS:
            continue

        try:
            better = _rewrite(backend, labels.get(question_id, ""), value)
        except Exception:                       # noqa: BLE001 - see docstring
            logger.warning("could not rewrite %s; keeping it as recorded", question_id)
            continue

        if better and better != value:
            out[question_id] = {**payload, "value": better}
            rewritten += 1

    logger.info("polished %s answer(s) of %s", rewritten, len(answers))
    return out, rewritten
