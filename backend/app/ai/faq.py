"""What the interviewee asks about the interview itself.

"Qui es-tu ?", "pourquoi cet entretien ?", "que devient ma reponse ?" are fair
questions, and not one of them is a glossary term. Routing them through the
referential search produced "Ce terme ne figure pas dans le referentiel" - a
non-answer to a question the assistant knows perfectly well, and the fastest
way to make an interviewee stop trusting the thing.

Deterministic and matched on the WHOLE message, like courtesy and navigation.
These are exactly the cases where a 3B model's judgement is worth nothing: the
question is unmistakable and the right answer is fixed. Every answer is built
from deployment configuration, so no client name is compiled into the product.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from app.core.config import settings

from . import social

# Matching runs on folded text - lowercase, unaccented, trailing punctuation
# removed - so these patterns must never carry an accent themselves.
_TOPICS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "identite",
        re.compile(
            r"^(?:"
            # "qui est tu" is the spoken form, and by far the most common way
            # this actually arrives - it was the very first one we lost.
            r"(?:mais\s+)?qui\s+(?:es[- ]?tu|est[- ]?tu|etes[- ]?vous|"
            r"est[- ]ce\s+que\s+tu\s+es)|"
            r"(?:tu|vous)\s+(?:es|etes)\s+qui|"
            r"c'?est\s+qui\s+(?:toi|vous)|"
            r"(?:c'?est\s+quoi|qu'?est[- ]ce\s+que)\s+(?:c'?est\s+que\s+)?argus|"
            r"(?:es[- ]?tu|etes[- ]vous|tu\s+es|vous\s+etes)\s+(?:un\s+|une\s+)?"
            r"(?:robot|bot|humain|machine|ia|intelligence\s+artificielle|ordinateur|"
            r"programme|logiciel|vraie?\s+personne)|"
            r"je\s+parle\s+a\s+(?:qui|un\s+robot|une\s+machine|un\s+humain|une\s+ia)|"
            r"presente[- ]toi|presentez[- ]vous"
            r")\s*\??$"
        ),
    ),
    (
        "organisateur",
        re.compile(
            r"^(?:"
            r"(?:c'?est\s+quoi|qu'?est[- ]ce\s+que\s+c'?est\s+que|qui\s+est|"
            r"qu'?est[- ]ce\s+que|connais[- ]tu|connaissez[- ]vous|"
            r"tu\s+connais|vous\s+connaissez|parle[- ]moi\s+de|parlez[- ]moi\s+de|"
            r"c'?est\s+qui)\s+"
            r"(?:la\s+societe\s+|l'?entreprise\s+|le\s+cabinet\s+|la\s+boite\s+)?"
            r"(?:%s|%s)"
            r")\s*\??$"
            % (
                re.escape(social._fold(settings.CONSULTING_ORG)),
                re.escape(social._fold(settings.CLIENT_NAME)),
            )
        ),
    ),
    (
        "objectif",
        re.compile(
            r"^(?:"
            r"pourquoi\s+.{0,45}?"
            r"(?:entretien|atelier|questionnaire|exercice|etat\s+des\s+lieux|questions?)|"
            r"(?:a\s+quoi|pour\s+quoi)\s+(?:ca\s+|cela\s+)?(?:sert|va\s+servir|servent).{0,30}|"
            r"quel\s+est\s+(?:le\s+but|l'?objectif|l'?interet|le\s+sens|l'?enjeu).{0,45}|"
            r"(?:c'?est|ca\s+est)\s+pour\s+quoi.{0,20}|"
            r"dans\s+quel\s+but.{0,45}"
            r")\s*\??$"
        ),
    ),
    (
        "duree",
        re.compile(
            r"^(?:"
            r"combien\s+de\s+temps.{0,35}|"
            r"(?:ca|cela)\s+(?:va\s+)?dure.{0,35}|"
            r"c'?est\s+long.{0,20}|"
            r"(?:il\s+y\s+a\s+)?combien\s+de\s+questions?.{0,25}|"
            r"il\s+(?:en\s+)?reste\s+combien.{0,25}"
            r")\s*\??$"
        ),
    ),
    (
        "donnees",
        re.compile(
            r"^(?:"
            r"(?:que|qu'?est[- ]ce\s+qu(?:e|i))\s+(?:vous\s+|tu\s+)?"
            r"(?:faites|fais|devien(?:nen)?t|advient|arrive).{0,45}"
            r"(?:reponses?|donnees?|informations?).{0,25}|"
            r"(?:ou|a\s+qui)\s+(?:vont|va|partent|sont).{0,45}|"
            r"qui\s+(?:va\s+|peut\s+|pourra\s+)?"
            r"(?:lit|lire|lira|voit|voir|verra|consulte|consulter|aura\s+acces|"
            r"a\s+acces|recoit|recevra).{0,45}|"
            r"(?:est[- ]ce\s+)?(?:que\s+)?(?:c'?est\s+)?confidentiel.{0,30}|"
            r"mes\s+reponses\s+sont[- ]elles\s+confidentielles.{0,20}"
            r")\s*\??$"
        ),
    ),
    (
        "reprise",
        re.compile(
            r"^(?:"
            r"(?:est[- ]ce\s+que\s+)?(?:je\s+peux|puis[- ]je|on\s+peut|peut[- ]on)\s+"
            r"(?:m'?)?(?:arreter|interrompre|faire\s+une\s+pause|reprendre|"
            r"terminer\s+plus\s+tard|finir\s+plus\s+tard|continuer\s+plus\s+tard|"
            r"revenir\s+plus\s+tard).{0,35}|"
            r"(?:mes\s+reponses\s+)?(?:sont[- ]elles\s+)?"
            r"(?:sauvegardees?|enregistrees?|conservees?).{0,25}"
            r")\s*\??$"
        ),
    ),
    (
        "fonctionnement",
        re.compile(
            r"^(?:"
            r"comment\s+(?:ca\s+(?:marche|fonctionne)|cela\s+fonctionne|"
            r"(?:je\s+)?(?:dois\s+)?(?:repondre|faire|proceder)).{0,30}|"
            r"(?:que|qu'?est[- ]ce\s+que)\s+(?:je\s+peux|puis[- ]je)\s+"
            r"(?:faire|vous\s+demander|te\s+demander).{0,25}|"
            r"(?:j'?ai\s+besoin\s+d'?)?aide|help|"
            r"quelles\s+sont\s+(?:les\s+|vos\s+)?(?:options|commandes|possibilites).{0,20}"
            r")\s*\??$"
        ),
    ),
]


def _programme() -> str:
    label = settings.PROGRAMME_LABEL
    return f"{label} de {settings.CLIENT_NAME}" if label else f"les travaux de {settings.CLIENT_NAME}"


def _answers(assistant_name: str, total: int) -> Dict[str, str]:
    org = settings.CONSULTING_ORG
    return {
        "identite": (
            f"Je suis **{assistant_name}**, l'assistant d'entretien mis en place par {org} "
            f"pour {_programme()}. Je ne suis pas un collaborateur : je suis un programme "
            "qui conduit cet atelier, note vos réponses et les met en forme dans le "
            "document officiel.\n\n"
            "Chaque réponse vous est soumise pour vérification avant d'être enregistrée, "
            f"et un consultant {org} relit l'ensemble ensuite."
        ),
        # Deliberately says what each party is *in this workshop*, and nothing
        # more. A description of the firm itself is not something this tool can
        # be authoritative about, and inventing one would be worse than useless.
        "organisateur": (
            f"**{org}** est le cabinet de conseil qui accompagne "
            f"{settings.CLIENT_NAME} sur "
            f"{settings.PROGRAMME_LABEL or 'ces travaux'} et qui conduit cet atelier ; "
            "c'est l'équipe qui exploitera les états des lieux collectés. "
            f"**{settings.CLIENT_NAME}** est l'organisation dont votre entité fait "
            "partie, et pour laquelle nous documentons la continuité d'activité.\n\n"
            f"Pour toute question sur la mission elle-même, votre interlocuteur est "
            f"{settings.CONTACT_NAME} — {settings.CONTACT_EMAIL}."
        ),
        "objectif": (
            "Cet entretien sert à établir l'**état des lieux** de votre entité pour "
            f"{_programme()}. Il s'agit de recenser ce que fait votre structure, ce dont "
            "elle dépend pour fonctionner, et ce qui se passerait en cas d'interruption : "
            "les activités, les applications, les données, les interlocuteurs et les "
            "périodes sensibles.\n\n"
            "Vos réponses alimentent directement le document de référence de votre entité, "
            "qui sert de matière de départ aux travaux de continuité d'activité. Personne "
            "ne connaît votre structure mieux que vous : c'est la raison de cet échange."
        ),
        "duree": (
            # The count comes from the plan actually loaded, so the two templates
            # never quote each other's length.
            (f"Il y a **{total} points** à parcourir, posés un par un. " if total > 0
             else "Les points sont parcourus un par un. ")
            + "Comptez généralement trente à quarante-cinq minutes, selon le niveau de "
            "détail que vous souhaitez donner.\n\n"
            "Rien ne presse : chaque réponse est enregistrée au fur et à mesure, vous "
            "pouvez vous arrêter et reprendre plus tard là où vous en étiez."
        ),
        "donnees": (
            "Vos réponses sont chiffrées dès leur enregistrement et ne servent qu'à remplir "
            "le document d'état des lieux de votre entité. Elles sont destinées à l'équipe "
            f"{org} qui accompagne {_programme()}, et à personne d'autre.\n\n"
            "Rien n'est enregistré sans votre validation : chaque réponse vous est "
            "présentée telle qu'elle sera écrite dans le document, et vous pouvez la "
            "corriger avant de confirmer."
        ),
        "reprise": (
            "Oui, sans difficulté. Chaque réponse confirmée est enregistrée immédiatement : "
            "vous pouvez fermer la fenêtre et revenir plus tard, l'entretien reprendra "
            "exactement là où vous l'aviez laissé.\n\n"
            "Vous pouvez aussi revenir sur un point déjà traité à tout moment, en le "
            "sélectionnant dans le panneau de gauche."
        ),
        "fonctionnement": (
            "Je pose les questions une par une. Répondez avec vos mots : je mets en forme, "
            "puis je vous montre le tableau tel qu'il sera écrit dans le document, pour que "
            "vous le corrigiez avant de confirmer.\n\n"
            "À tout moment, vous pouvez me demander **la définition** d'un terme, **un "
            "exemple** de réponse attendue, **passer** une question pour y revenir plus "
            "tard, ou reprendre un point déjà traité depuis le panneau de gauche."
        ),
    }


def match(message: str) -> Optional[str]:
    """The topic this message asks about, or None if it is not a meta question."""
    folded = social._fold(message)
    # A long message is an answer that happens to contain a question mark, not a
    # question about the workshop.
    if not folded or len(folded) > 120:
        return None
    for topic, pattern in _TOPICS:
        if pattern.match(folded):
            return topic
    return None


def answer(topic: str, assistant_name: str, question_prompt: str, total: int) -> str:
    """The reply, re-anchored on the question the interview is waiting for."""
    body = _answers(assistant_name, total)[topic]
    return f"{body}\n\nPour revenir à notre point : {question_prompt}"

# Phrasings that really are asking what a term means. A miss on one of these
# deserves "not in the referential, noted for the consultant" - which is both
# accurate and useful. Anything else that got this far is simply off-topic.
_DEFINITION_REQUEST = re.compile(
    r"(?:que\s+(?:signifie|veut\s+dire|veux[- ]tu\s+dire|voulez[- ]vous\s+dire)|"
    r"qu'?est[- ]ce\s+que|c'?est\s+quoi|"
    r"(?:la\s+)?definition\s+(?:de|du|d')|"
    r"je\s+ne\s+(?:comprends|connais)\s+pas|"
    r"(?:ca|cela)\s+veut\s+dire\s+quoi|"
    r"vous\s+entendez\s+quoi\s+par|tu\s+entends\s+quoi\s+par)"
)


def asks_for_a_definition(message: str) -> bool:
    return bool(_DEFINITION_REQUEST.search(social._fold(message)))


def out_of_scope(question_prompt: str) -> str:
    """For anything the workshop has no business answering.

    Better than a glossary miss dressed up as one: it says plainly that the
    request is outside what this assistant does, states what it *is* for, and
    points at a human. Nothing is invented and nothing is promised.
    """
    org = settings.CONSULTING_ORG
    return (
        "Désolé, cela sort de mon champ. Je suis un assistant dédié à un seul rôle : "
        f"conduire l'entretien d'état des lieux de votre entité pour {_programme()} — "
        "recenser vos activités, vos applications, vos données et vos dépendances, "
        "puis les mettre en forme dans le document officiel.\n\n"
        f"Pour tout le reste, votre interlocuteur est {settings.CONTACT_NAME} — "
        f"{settings.CONTACT_EMAIL}. Je note votre question pour le consultant {org}.\n\n"
        "Sur cet atelier, en revanche, je peux vous donner **la définition** d'un terme "
        "du référentiel, **un exemple** de réponse attendue, ou **passer** la question "
        "pour y revenir plus tard.\n\n"
        f"Pour revenir à notre point : {question_prompt}"
    )
