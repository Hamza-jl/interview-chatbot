"""Knowledge base used when the user asks a question instead of answering one.

Tier 1 entries are *verbatim definitions taken from the client's own templates*
themselves - they are the authoritative source and are quoted as such.
Tier 2 entries are standard PCA / ISO 22301 vocabulary that an interviewee
routinely asks about mid-interview.

The corpus is small (a few kB), so retrieval is a transparent lexical score
rather than a vector index: it is auditable, deterministic, and adds no
infrastructure to a system that handles confidential banking data.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Entry:
    term: str
    definition: str
    source: str
    aliases: tuple[str, ...] = ()


TEMPLATE_SOURCE = "Modèle client - État des lieux"
DOMAIN_SOURCE = "Referentiel PCA Devoteam / ISO 22301"


GLOSSARY: List[Entry] = [
    # ---------------- Tier 1: definitions written in the templates ---------
    Entry(
        term="Criticite SI (V / C / MC / PC)",
        definition=(
            "Niveau de dépendance d'un processus métier à une application :\n"
            "- Vitale (V) : le processus métier est arrêté en cas d'indisponibilité de l'application ;\n"
            "- Critique (C) : le processus nécessite un travail manuel pour contourner l'application ;\n"
            "- Moyennement critique (MC) : le processus nécessite un contournement de l'application "
            "indisponible par une autre application ;\n"
            "- Peu critique (PC) : le processus métier reste opérationnel et est peu impacté."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("criticite", "vitale", "critique", "moyennement critique", "peu critique",
                 "criticite application", "niveau de criticité si", "criticite si",
                 "v c mc pc", "v/c/mc/pc", "vcmcpc"),
    ),
    Entry(
        term="Niveau de criticité d'un flux interne (A / B / C / D)",
        definition=(
            "Criticité d'un échange d'informations avec un correspondant interne :\n"
            "- A : ne peut pas être traité manuellement (le SI est indispensable) ;\n"
            "- B : peut être traité manuellement de facon limitée dans le temps ;\n"
            "- C : peut etre traite manuellement ;\n"
            "- D : peut etre arrete."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("flux interne", "niveau de criticité", "criticite flux", "abcd",
                 "echanges internes", "criticite echange"),
    ),
    Entry(
        term="Collaborateur cle",
        definition=(
            "Est considéré comme collaborateur clé :\n"
            "- tout collaborateur qui dispose d'une expertise rare ou pointue ;\n"
            "- tout collaborateur qui assure une tache tout seul ;\n"
            "- tout collaborateur dont le potentiel d'encadrement est affirme au sein de l'équipe."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("collaborateurs cles", "personne cle", "homme cle", "expertise rare",
                 "sans binome", "suppleant"),
    ),
    Entry(
        term="Typologie de correspondants (Mono / Multi)",
        definition=(
            "Pour les échanges externes, il convient de préciser la typologie du correspondant :\n"
            "- Mono-correspondant : un seul interlocuteur possible, en precisant s'il est ou non "
            "en situation de monopole ;\n"
            "- Multi-correspondants : plusieurs interlocuteurs alternatifs existent."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("mono correspondant", "multi correspondants", "monopole", "typologie",
                 "correspondant externe"),
    ),
    Entry(
        term="Contraintes operationnelles",
        definition=(
            "Exigences réglementaires, juridiques, contractuelles ou de confidentialite qui "
            "pesent sur un processus et limitent la facon dont il peut être execute ou "
            "contourne en situation degradee."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("contrainte", "exigence reglementaire", "obligation legale", "contrainte juridique"),
    ),
    Entry(
        term="Periodes critiques",
        definition=(
            "Périodes de forte activité ou a forts enjeux pour l'entité, par exemple la cloture "
            "mensuelle ou annuelle, ou le debut de mois. Une interruption survenant pendant ces "
            "périodes à un impact nettement superieur."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("periode critique", "pic d'activite", "cloture", "saisonnalite"),
    ),
    Entry(
        term="Couverture fonctionnelle",
        definition=(
            "Perimetre reellement couvert par une application au sein d'un processus : quelles "
            "étapes du processus l'outil prend en charge, et lesquelles restent manuelles."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("couverture", "perimetre applicatif"),
    ),
    Entry(
        term="Contournement envisageable",
        definition=(
            "Mode operatoire de secours permettant de poursuivre le processus métier lorsque "
            "l'application est indisponible : procédure manuelle, application alternative, "
            "ou report de traitement - en precisant la durée pendant laquelle il reste tenable."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("contournement", "mode degrade", "solution de secours", "workaround"),
    ),
    Entry(
        term="Vis-a-vis",
        definition=(
            "Dans la fiche de suivi, le ou les interlocuteurs de l'entité rencontres lors de "
            "l'atelier d'État des lieux, par opposition au rédacteur qui formalise le compte rendu."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("interlocuteur", "vis a vis"),
    ),
    Entry(
        term="Macro activite",
        definition=(
            "Activité opérationnelle concrète réalisée dans le cadre d'un processus. Elle se "
            "situe entre le processus (vue d'ensemble) et la tache elementaire (geste métier)."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("macro-activite", "activite", "macro activites"),
    ),
    # ---------------- Tier 2: PCA vocabulary --------------------------------
    Entry(
        term="PCA - Plan de Continuité d'Activité",
        definition=(
            "Ensemble documente de procédures et de moyens permettant à un organisme de "
            "poursuivre ses activités essentielles à un niveau acceptable predefini lors d'une "
            "interruption, puis de revenir à un fonctionnement normal."
        ),
        source=DOMAIN_SOURCE,
        aliases=("plan de continuité", "continuite d'activite", "bcp", "business continuity"),
    ),
    Entry(
        term="BIA - Bilan d'Impact sur l'Activité",
        definition=(
            "Analyse qui identifié les activités critiques d'une entité, évalué les conséquences "
            "d'une interruption dans le temps (financieres, réglementaires, image, humaines) et "
            "en deduit les objectifs de reprise (DMIA / RTO et PDMA / RPO)."
        ),
        source=DOMAIN_SOURCE,
        aliases=("bia", "business impact analysis", "bilan d'impact", "analyse d'impact"),
    ),
    Entry(
        term="DMIA / RTO - Duree Maximale d'Interruption Admissible",
        definition=(
            "Délai maximal pendant lequel une activité peut rester indisponible avant que les "
            "conséquences ne deviennent inacceptables. C'est la cible de délai de reprise."
        ),
        source=DOMAIN_SOURCE,
        aliases=("dmia", "rto", "duree maximale d'interruption", "délai de reprise"),
    ),
    Entry(
        term="PDMA / RPO - Perte de Données Maximale Admissible",
        definition=(
            "Volume de données, exprime en temps, qu'une entité accepte de perdre en cas de "
            "sinistre. Il determine la fréquence des sauvegardes et des replications."
        ),
        source=DOMAIN_SOURCE,
        aliases=("pdma", "rpo", "perte de données", "fréquence de sauvegarde"),
    ),
    Entry(
        term="PSI - Plan de Secours Informatique",
        definition=(
            "Volet technique du PCA : dispositif permettant de redemarrer les systèmes "
            "d'information sur un site ou une infrastructure de secours dans les délais cibles. "
            "Également appele PRA (Plan de Reprise d'Activité) ou DRP."
        ),
        source=DOMAIN_SOURCE,
        aliases=("psi", "pra", "drp", "plan de reprise", "plan de secours", "site de secours"),
    ),
    Entry(
        term="SDSI - Schema Directeur des Systèmes d'Information",
        definition=(
            "Document stratégique qui aligne le système d'information sur la stratégie de "
            "l'entreprise et definit la trajectoire d'évolution du SI sur 3 a 5 ans."
        ),
        source=DOMAIN_SOURCE,
        aliases=("sdsi", "schema directeur"),
    ),
    Entry(
        term="SMCA - Système de Management de la Continuité d'Activité",
        definition=(
            "Dispositif de gouvernance, au sens de la norme ISO 22301, qui pilote la mise en "
            "place, le maintien en conditions opérationnelles et l'amelioration continue du PCA."
        ),
        source=DOMAIN_SOURCE,
        aliases=("smca", "iso 22301", "management de la continuité"),
    ),
    Entry(
        term="Processus metier",
        definition=(
            "Enchainement d'activités qui transforme des entrées en un résultat ayant une valeur "
            "pour un client interne ou externe. C'est la maille a laquelle le PCA évalué la "
            "criticité et fixe les objectifs de reprise."
        ),
        source=DOMAIN_SOURCE,
        aliases=("processus", "process"),
    ),
    Entry(
        term="Domaine",
        definition=(
            "Regroupement fonctionnel de haut niveau qui rassemble plusieurs processus de même "
            "nature (par exemple : Crédit, Monétique, Production informatique, Ressources Humaines)."
        ),
        source=DOMAIN_SOURCE,
        aliases=("domaine fonctionnel", "grand domaine"),
    ),
    Entry(
        term="Mode degrade",
        definition=(
            "Fonctionnement transitoire durant lequel l'activité se poursuit avec des moyens "
            "reduits - procédures manuelles, service partiel - en attendant le retour à la normale."
        ),
        source=DOMAIN_SOURCE,
        aliases=("degrade", "fonctionnement degrade", "procedure manuelle"),
    ),
    Entry(
        term="SLA - Accord de niveau de service",
        definition=(
            "Engagement contractuel d'un fournisseur sur un niveau de service mesurable "
            "(disponibilité, délai de retablissement, temps de réponse), assorti le cas echeant "
            "de penalites."
        ),
        source=DOMAIN_SOURCE,
        aliases=("sla", "niveau de service", "engagement de service"),
    ),
    Entry(
        term="Obsolescence technique",
        definition=(
            "Situation dans laquelle un composant matériel ou logiciel n'est plus supporte par "
            "son editeur ou constructeur, ce qui prive l'organisation de correctifs de sécurité "
            "et augmente le risque d'indisponibilité."
        ),
        source=DOMAIN_SOURCE,
        aliases=("obsolescence", "fin de support", "end of life", "eol"),
    ),
    Entry(
        term="Urbanisation du SI",
        definition=(
            "Discipline qui organisé le système d'information en zones, quartiers et blocs "
            "fonctionnels coherents afin de maitriser les dépendances et de faciliter son évolution."
        ),
        source=DOMAIN_SOURCE,
        aliases=("urbanisation", "cartographie applicative", "architecture applicative"),
    ),
    Entry(
        term="CAPEX / OPEX",
        definition=(
            "CAPEX : depenses d'investissement, amorties dans le temps (achat de serveurs, "
            "licences perpetuelles). OPEX : depenses de fonctionnement recurrentes "
            "(abonnements cloud, maintenance, infogerance)."
        ),
        source=DOMAIN_SOURCE,
        aliases=("capex", "opex", "budget it", "investissement"),
    ),
    Entry(
        term="Infogerance",
        definition=(
            "Delegation contractuelle à un prestataire externe de tout ou partie de "
            "l'exploitation du système d'information."
        ),
        source=DOMAIN_SOURCE,
        aliases=("infogerance", "outsourcing", "tierce maintenance", "tma"),
    ),
]


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
_STOP = {
    "que", "quoi", "est", "ce", "une", "un", "des", "les", "la", "le", "de", "du", "dans",
    "pour", "par", "sur", "avec", "vous", "je", "il", "elle", "on", "nous", "quel", "quelle",
    "quels", "quelles", "comment", "pourquoi", "signifie", "veut", "dire", "expliquer",
    "explique", "definition", "cest", "et", "ou", "au", "aux", "en", "pas", "plus", "moi",
    "tu", "me", "mon", "ma", "mes", "votre", "vos", "son", "sa", "ses", "cela", "ca",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # Collapse runs of spaces: punctuation used to leave gaps wide enough that
    # a multi-word alias such as "v c mc pc" never matched "(V, C, MC, PC)".
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> List[str]:
    return [t for t in _norm(text).split() if len(t) > 2 and t not in _STOP]


# Scoring: whole-phrase term/alias hit = 8+, each shared term token = 3.0,
# each shared body word = 0.5.
#
# The floor sits above a single shared term token on purpose. "Des donnees
# personnelles tres sensibles" shares the word "donnees" with the PDMA entry and
# used to come back as a definition of PDMA - an answer, met with a lecture.
# Clearing 6.0 needs either a real phrase match or two term tokens.
MIN_RELEVANCE = 6.0


def search(query: str, limit: int = 3) -> List[Entry]:
    """Score entries by term / alias / body overlap. Deterministic and auditable.

    Returns [] when nothing clears MIN_RELEVANCE - saying "ce terme ne figure
    pas dans le référentiel" is far better than serving a near-miss définition.
    """
    q_norm = _norm(query)
    if not q_norm:
        return []
    # Deliberately NOT gated on q_tokens: the tokenizer drops words of two
    # characters or fewer, so "(V, C, MC, PC)" tokenises to nothing. Returning
    # early there meant the phrase match below never ran and the question the
    # template itself asks - "criticite SI (V, C, MC, PC)" - had no answer.
    q_tokens = _tokens(query)

    scored: List[tuple[float, int, Entry]] = []
    for idx, entry in enumerate(GLOSSARY):
        term_n = _norm(entry.term)
        score = 0.0

        # Whole-phrase hits on the term or an alias dominate.
        for alias in (entry.term, *entry.aliases):
            a = _norm(alias).strip()
            if a and a in q_norm:
                score += 8.0 + len(a.split())

        term_tokens = set(_tokens(entry.term)) | {
            t for alias in entry.aliases for t in _tokens(alias)
        }
        score += 3.0 * len(term_tokens & set(q_tokens))

        body_tokens = set(_tokens(entry.definition))
        score += 0.5 * len(body_tokens & set(q_tokens))

        if score >= MIN_RELEVANCE:
            scored.append((score, -idx, entry))

    scored.sort(reverse=True)
    return [e for _, _, e in scored[:limit]]


def render_context(entries: List[Entry]) -> str:
    if not entries:
        return "(aucune définition correspondante dans le référentiel)"
    return "\n\n".join(
        f"### {e.term}\n{e.definition}\n(Source : {e.source})" for e in entries
    )


def full_corpus() -> str:
    """The entire glossary - small enough to sit in a cached system prompt."""
    return "\n\n".join(f"### {e.term}\n{e.definition}\n(Source : {e.source})" for e in GLOSSARY)
