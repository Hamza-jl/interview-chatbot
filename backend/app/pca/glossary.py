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


TEMPLATE_SOURCE = "Modele client - Etat des lieux"
DOMAIN_SOURCE = "Referentiel PCA Devoteam / ISO 22301"


GLOSSARY: List[Entry] = [
    # ---------------- Tier 1: definitions written in the templates ---------
    Entry(
        term="Criticite SI (V / C / MC / PC)",
        definition=(
            "Niveau de dependance d'un processus metier a une application :\n"
            "- Vitale (V) : le processus metier est arrete en cas d'indisponibilite de l'application ;\n"
            "- Critique (C) : le processus necessite un travail manuel pour contourner l'application ;\n"
            "- Moyennement critique (MC) : le processus necessite un contournement de l'application "
            "indisponible par une autre application ;\n"
            "- Peu critique (PC) : le processus metier reste operationnel et est peu impacte."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("criticite", "vitale", "critique", "moyennement critique", "peu critique",
                 "criticite application", "niveau de criticite si", "criticite si",
                 "v c mc pc", "v/c/mc/pc", "vcmcpc"),
    ),
    Entry(
        term="Niveau de criticite d'un flux interne (A / B / C / D)",
        definition=(
            "Criticite d'un echange d'informations avec un correspondant interne :\n"
            "- A : ne peut pas etre traite manuellement (le SI est indispensable) ;\n"
            "- B : peut etre traite manuellement de facon limitee dans le temps ;\n"
            "- C : peut etre traite manuellement ;\n"
            "- D : peut etre arrete."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("flux interne", "niveau de criticite", "criticite flux", "abcd",
                 "echanges internes", "criticite echange"),
    ),
    Entry(
        term="Collaborateur cle",
        definition=(
            "Est considere comme collaborateur cle :\n"
            "- tout collaborateur qui dispose d'une expertise rare ou pointue ;\n"
            "- tout collaborateur qui assure une tache tout seul ;\n"
            "- tout collaborateur dont le potentiel d'encadrement est affirme au sein de l'equipe."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("collaborateurs cles", "personne cle", "homme cle", "expertise rare",
                 "sans binome", "suppleant"),
    ),
    Entry(
        term="Typologie de correspondants (Mono / Multi)",
        definition=(
            "Pour les echanges externes, il convient de preciser la typologie du correspondant :\n"
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
            "Exigences reglementaires, juridiques, contractuelles ou de confidentialite qui "
            "pesent sur un processus et limitent la facon dont il peut etre execute ou "
            "contourne en situation degradee."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("contrainte", "exigence reglementaire", "obligation legale", "contrainte juridique"),
    ),
    Entry(
        term="Periodes critiques",
        definition=(
            "Periodes de forte activite ou a forts enjeux pour l'entite, par exemple la cloture "
            "mensuelle ou annuelle, ou le debut de mois. Une interruption survenant pendant ces "
            "periodes a un impact nettement superieur."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("periode critique", "pic d'activite", "cloture", "saisonnalite"),
    ),
    Entry(
        term="Couverture fonctionnelle",
        definition=(
            "Perimetre reellement couvert par une application au sein d'un processus : quelles "
            "etapes du processus l'outil prend en charge, et lesquelles restent manuelles."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("couverture", "perimetre applicatif"),
    ),
    Entry(
        term="Contournement envisageable",
        definition=(
            "Mode operatoire de secours permettant de poursuivre le processus metier lorsque "
            "l'application est indisponible : procedure manuelle, application alternative, "
            "ou report de traitement - en precisant la duree pendant laquelle il reste tenable."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("contournement", "mode degrade", "solution de secours", "workaround"),
    ),
    Entry(
        term="Vis-a-vis",
        definition=(
            "Dans la fiche de suivi, le ou les interlocuteurs de l'entite rencontres lors de "
            "l'atelier d'etat des lieux, par opposition au redacteur qui formalise le compte rendu."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("interlocuteur", "vis a vis"),
    ),
    Entry(
        term="Macro activite",
        definition=(
            "Activite operationnelle concrete realisee dans le cadre d'un processus. Elle se "
            "situe entre le processus (vue d'ensemble) et la tache elementaire (geste metier)."
        ),
        source=TEMPLATE_SOURCE,
        aliases=("macro-activite", "activite", "macro activites"),
    ),
    # ---------------- Tier 2: PCA vocabulary --------------------------------
    Entry(
        term="PCA - Plan de Continuite d'Activite",
        definition=(
            "Ensemble documente de procedures et de moyens permettant a un organisme de "
            "poursuivre ses activites essentielles a un niveau acceptable predefini lors d'une "
            "interruption, puis de revenir a un fonctionnement normal."
        ),
        source=DOMAIN_SOURCE,
        aliases=("plan de continuite", "continuite d'activite", "bcp", "business continuity"),
    ),
    Entry(
        term="BIA - Bilan d'Impact sur l'Activite",
        definition=(
            "Analyse qui identifie les activites critiques d'une entite, evalue les consequences "
            "d'une interruption dans le temps (financieres, reglementaires, image, humaines) et "
            "en deduit les objectifs de reprise (DMIA / RTO et PDMA / RPO)."
        ),
        source=DOMAIN_SOURCE,
        aliases=("bia", "business impact analysis", "bilan d'impact", "analyse d'impact"),
    ),
    Entry(
        term="DMIA / RTO - Duree Maximale d'Interruption Admissible",
        definition=(
            "Delai maximal pendant lequel une activite peut rester indisponible avant que les "
            "consequences ne deviennent inacceptables. C'est la cible de delai de reprise."
        ),
        source=DOMAIN_SOURCE,
        aliases=("dmia", "rto", "duree maximale d'interruption", "delai de reprise"),
    ),
    Entry(
        term="PDMA / RPO - Perte de Donnees Maximale Admissible",
        definition=(
            "Volume de donnees, exprime en temps, qu'une entite accepte de perdre en cas de "
            "sinistre. Il determine la frequence des sauvegardes et des replications."
        ),
        source=DOMAIN_SOURCE,
        aliases=("pdma", "rpo", "perte de donnees", "frequence de sauvegarde"),
    ),
    Entry(
        term="PSI - Plan de Secours Informatique",
        definition=(
            "Volet technique du PCA : dispositif permettant de redemarrer les systemes "
            "d'information sur un site ou une infrastructure de secours dans les delais cibles. "
            "Egalement appele PRA (Plan de Reprise d'Activite) ou DRP."
        ),
        source=DOMAIN_SOURCE,
        aliases=("psi", "pra", "drp", "plan de reprise", "plan de secours", "site de secours"),
    ),
    Entry(
        term="SDSI - Schema Directeur des Systemes d'Information",
        definition=(
            "Document strategique qui aligne le systeme d'information sur la strategie de "
            "l'entreprise et definit la trajectoire d'evolution du SI sur 3 a 5 ans."
        ),
        source=DOMAIN_SOURCE,
        aliases=("sdsi", "schema directeur"),
    ),
    Entry(
        term="SMCA - Systeme de Management de la Continuite d'Activite",
        definition=(
            "Dispositif de gouvernance, au sens de la norme ISO 22301, qui pilote la mise en "
            "place, le maintien en conditions operationnelles et l'amelioration continue du PCA."
        ),
        source=DOMAIN_SOURCE,
        aliases=("smca", "iso 22301", "management de la continuite"),
    ),
    Entry(
        term="Processus metier",
        definition=(
            "Enchainement d'activites qui transforme des entrees en un resultat ayant une valeur "
            "pour un client interne ou externe. C'est la maille a laquelle le PCA evalue la "
            "criticite et fixe les objectifs de reprise."
        ),
        source=DOMAIN_SOURCE,
        aliases=("processus", "process"),
    ),
    Entry(
        term="Domaine",
        definition=(
            "Regroupement fonctionnel de haut niveau qui rassemble plusieurs processus de meme "
            "nature (par exemple : Credit, Monetique, Production informatique, Ressources Humaines)."
        ),
        source=DOMAIN_SOURCE,
        aliases=("domaine fonctionnel", "grand domaine"),
    ),
    Entry(
        term="Mode degrade",
        definition=(
            "Fonctionnement transitoire durant lequel l'activite se poursuit avec des moyens "
            "reduits - procedures manuelles, service partiel - en attendant le retour a la normale."
        ),
        source=DOMAIN_SOURCE,
        aliases=("degrade", "fonctionnement degrade", "procedure manuelle"),
    ),
    Entry(
        term="SLA - Accord de niveau de service",
        definition=(
            "Engagement contractuel d'un fournisseur sur un niveau de service mesurable "
            "(disponibilite, delai de retablissement, temps de reponse), assorti le cas echeant "
            "de penalites."
        ),
        source=DOMAIN_SOURCE,
        aliases=("sla", "niveau de service", "engagement de service"),
    ),
    Entry(
        term="Obsolescence technique",
        definition=(
            "Situation dans laquelle un composant materiel ou logiciel n'est plus supporte par "
            "son editeur ou constructeur, ce qui prive l'organisation de correctifs de securite "
            "et augmente le risque d'indisponibilite."
        ),
        source=DOMAIN_SOURCE,
        aliases=("obsolescence", "fin de support", "end of life", "eol"),
    ),
    Entry(
        term="Urbanisation du SI",
        definition=(
            "Discipline qui organise le systeme d'information en zones, quartiers et blocs "
            "fonctionnels coherents afin de maitriser les dependances et de faciliter son evolution."
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
            "Delegation contractuelle a un prestataire externe de tout ou partie de "
            "l'exploitation du systeme d'information."
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
    pas dans le referentiel" is far better than serving a near-miss definition.
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
        return "(aucune definition correspondante dans le referentiel)"
    return "\n\n".join(
        f"### {e.term}\n{e.definition}\n(Source : {e.source})" for e in entries
    )


def full_corpus() -> str:
    """The entire glossary - small enough to sit in a cached system prompt."""
    return "\n\n".join(f"### {e.term}\n{e.definition}\n(Source : {e.source})" for e in GLOSSARY)
