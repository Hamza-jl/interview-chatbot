"""Conversational courtesy: greetings, thanks, acknowledgements.

An interview is a conversation, so people open with "bonjour", say "merci", and
answer "d'accord". None of that is interview content, and consigning it into an
audit document is a defect - "bonjour" must never end up in the "Nom du
Responsable" cell.

This runs **before** any model call, for three reasons:

* it is deterministic, so a greeting can never be misclassified;
* it costs nothing, where a model call costs seconds;
* it also handles the common mixed case - "Bonjour, le responsable est Mme Ben
  Ammar" - by stripping the courtesy opener and passing the substance on.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal, Optional, Tuple

Category = Literal["salutation", "remerciement", "acquiescement", "politesse"]

# Courtesy openers that may precede a real answer. Stripped, not rejected.
_OPENER = re.compile(
    r"^\s*(?:(?:re)?bonjour|bonsoir|salut|coucou|hello|hi|hey|bjr|slt|"
    r"bonne\s+journee|bonne\s+soiree)\b[\s,;:!.’'-]*",
    re.IGNORECASE,
)

# A message that is *only* one of these carries no interview content.
_WHOLE: list[tuple[Category, re.Pattern[str]]] = [
    (
        "salutation",
        re.compile(
            r"^(?:(?:re)?bonjour|bonsoir|salut|coucou|hello|hi|hey|bjr|slt|"
            r"bonne\s+journee|bonne\s+soiree|enchante[e]?|"
            r"(?:tres\s+)?heureux\s+de\s+vous\s+(?:parler|rencontrer))"
            r"(?:\s+(?:a\s+vous|monsieur|madame|tout\s+le\s+monde))?$"
        ),
    ),
    (
        "remerciement",
        re.compile(r"^(?:merci(?:\s+(?:beaucoup|bien|a\s+vous))?|je\s+vous\s+remercie|thanks?)$"),
    ),
    (
        "acquiescement",
        re.compile(
            r"^(?:ok(?:ay)?|d'?accord|tres\s+bien|parfait|entendu|compris|c'?est\s+note|"
            r"ca\s+marche|bien\s+sur|oui|volontiers|allons[- ]y|je\s+vous\s+ecoute|"
            r"c'?est\s+parti|super)$"
        ),
    ),
    (
        "politesse",
        re.compile(
            r"^(?:au\s+revoir|a\s+bientot|bonne\s+continuation|"
            r"(?:et\s+)?(?:vous|toi)\s*\?|ca\s+va\s*\??|comment\s+allez[- ]vous\s*\??|"
            r"comment\s+ca\s+va\s*\??)$"
        ),
    ),
]


def _fold(text: str) -> str:
    """Lowercase, strip accents and trailing punctuation for matching only."""
    folded = unicodedata.normalize("NFKD", (text or "").strip().lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[\s!.?,;:…]+$", "", folded).strip()


def classify_social(text: str) -> Optional[Category]:
    """Category if the message is *entirely* courtesy, else None."""
    folded = _fold(text)
    if not folded or len(folded) > 60:
        return None
    for category, pattern in _WHOLE:
        if pattern.match(folded):
            return category
    return None


def strip_opener(text: str) -> Tuple[bool, str]:
    """Remove a leading "Bonjour," so the rest can be processed normally.

    Returns (an opener was present, remaining text).
    """
    stripped = _OPENER.sub("", text or "", count=1)
    return stripped != (text or ""), stripped.strip()


def split(text: str) -> Tuple[Optional[Category], str]:
    """Returns (courtesy category if the whole message is courtesy, substance).

    ``("salutation", "")``  -> nothing to record, greet and re-ask.
    ``(None, "le responsable est ...")`` -> greeting stripped, process the rest.
    ``(None, original)``    -> nothing social about it.
    """
    category = classify_social(text)
    if category is not None:
        return category, ""

    had_opener, remainder = strip_opener(text)
    if had_opener and not remainder:
        return "salutation", ""
    return None, remainder if had_opener else (text or "").strip()


# --------------------------------------------------------------------------- #
# Replies
# --------------------------------------------------------------------------- #
_REPLY = {
    "salutation": (
        "Bonjour, et merci de prendre le temps de cet atelier. "
        "Je vous accompagne pas à pas ; nous pouvons commencer quand vous le souhaitez."
    ),
    "remerciement": "Je vous en prie.",
    "acquiescement": "Tres bien.",
    "politesse": "Tout va bien, merci. Poursuivons quand vous voulez.",
}

_FIRST_TURN = (
    "Bonjour, et bienvenue dans cet atelier d'État des lieux. "
    "Prenez le temps qu'il vous faut : je pose les questions une par une, et vous "
    "pouvez à tout moment me demander la définition d'un terme ou un exemple."
)


def reply(category: Category, question_prompt: str, first_turn: bool = False) -> str:
    """A courteous answer that re-anchors the interview on the current question."""
    opening = _FIRST_TURN if (first_turn and category == "salutation") else _REPLY[category]
    return f"{opening}\n\n{question_prompt}"


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
# Navigation is recognised on the WHOLE message only, for the same reason as
# courtesy. "Nous n'avons pas de comites" is an answer that happens to be
# negative; letting a model decide cost a real answer in a real interview, and
# the old skip regex matched the bare word "aucun" inside it.
_NAVIGATION: list[tuple[str, re.Pattern[str]]] = [
    (
        "suivant",
        re.compile(
            r"^(?:"
            r"(?:on\s+)?(?:peut[- ]on\s+)?(?:passer|passons|passe)(?:\s+(?:a\s+la\s+)?"
            r"(?:cette\s+)?(?:la\s+)?(?:question\s+)?(?:suivante?|suite))?|"
            r"question\s+suivante|suivant(?:e)?|skip|"
            r"je\s+(?:ne\s+)?(?:sais|dispose|connais|poss[eè]de)\s+pas"
            r"(?:\s+(?:(?:de|d'|du|des|cette|ces|la|le|les|l')\s*)*"
            r"(?:information|informations|reponse|donnee|donnees|element|elements))?"
            r"(?:\s+(?:pour\s+(?:le\s+)?(?:moment|instant)|maintenant|ici|actuellement))?|"
            r"(?:je\s+)?n'?\s*(?:en\s+)?ai\s+pas\s+(?:(?:de|d'|du|des|cette|ces|la|le|les|l')\s*)*"
            r"(?:information|informations|idee|reponse)"
            r"(?:\s+(?:pour\s+(?:le\s+)?(?:moment|instant)|maintenant))?|"
            r"(?:on\s+)?(?:verra|reviendra)\s+(?:plus\s+tard|apres)|plus\s+tard|"
            r"sans\s+objet|non\s+applicable|n\s*/\s*a"
            r")$"
        ),
    ),
    (
        "precedent",
        re.compile(
            r"^(?:(?:je\s+veux\s+)?(?:revenir|retour(?:ner)?|retour)"
            r"(?:\s+(?:a\s+la\s+|en\s+)?(?:question\s+)?(?:precedente?|arriere))?|"
            r"question\s+precedente|precedent(?:e)?|"
            r"(?:je\s+veux\s+)?corriger(?:\s+(?:ma\s+)?(?:reponse|precedente))?)$"
        ),
    ),
    (
        "repeter",
        re.compile(
            r"^(?:(?:pouvez[- ]vous\s+)?(?:repeter|redire|reformuler)"
            r"(?:\s+(?:la\s+)?question)?|"
            r"(?:quelle\s+(?:est|etait)\s+la\s+question)|je\s+n'?ai\s+pas\s+compris\s+la\s+question)$"
        ),
    ),
    (
        "terminer",
        re.compile(
            r"^(?:(?:je\s+veux\s+)?(?:terminer|arreter|finir|stopper|quitter)"
            r"(?:\s+(?:l'?\s*)?(?:entretien|atelier|maintenant))?|"
            r"c'?est\s+(?:fini|termine)|stop|fin\s+de\s+l'?entretien)$"
        ),
    ),
]


def classify_navigation(text: str) -> Optional[str]:
    """Navigation intent if the message is *entirely* a navigation phrase.

    A message carrying interview content - even a negative one - is never
    navigation, so a real answer cannot be discarded as a skip.
    """
    folded = _fold(text)
    if not folded or len(folded) > 70:
        return None
    for nav, pattern in _NAVIGATION:
        if pattern.match(folded):
            return nav
    return None


# --------------------------------------------------------------------------- #
# Requests for an example
# --------------------------------------------------------------------------- #
# "Un exemple ?" is not a glossary lookup. Searching the referential for it
# returned whichever entry happened to share a word - in one interview that was
# "Periodes critiques" for a question about activity mapping.
_EXAMPLE = re.compile(
    r"(?:donne[rz]?[- ]moi\s+un\s+exemple|un\s+exemple|par\s+exemple|"
    r"exemple\s+de\s+(?:reponse|remplissage)|comment\s+(?:dois[- ]je|je\s+dois)\s+repondre|"
    r"quel(?:le)?\s+(?:format|forme)|a\s+quoi\s+(?:ca\s+)?ressemble)"
)


def wants_example(text: str) -> bool:
    return bool(_EXAMPLE.search(_fold(text)))
