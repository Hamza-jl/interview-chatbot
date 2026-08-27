"""The interview plan, derived one-to-one from the two Word templates.

Every ``Question`` carries a ``Target`` describing the exact cell (or table) of
the source .docx it feeds.  The chatbot never invents structure: it walks this
plan, and ``docx_filler`` writes the collected answers back into the untouched
original document.

Table indices below are 1-based and match the order the tables appear in the
template files:

  État des lieux - DSI      : 17 tables
  État des lieux - Entité   : 14 tables
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

Kind = Literal["field", "open", "grid"]


@dataclass(frozen=True)
class Target:
    """Where an answer lands in the template."""

    table: int                    # 1-based table index
    row: Optional[int] = None     # for cell writes
    col: int = 1                  # for cell writes
    mode: Literal["cell", "rows"] = "cell"
    header_rows: int = 1          # for mode="rows": how many leading rows to keep


@dataclass(frozen=True)
class Column:
    id: str
    label: str
    hint: str = ""
    choices: Optional[List[str]] = None
    required: bool = True


@dataclass(frozen=True)
class Question:
    id: str
    kind: Kind
    section: str
    label: str
    prompt: str
    target: Target
    help: str = ""
    example: str = ""
    columns: List[Column] = field(default_factory=list)
    optional: bool = False
    min_rows: int = 1


# --------------------------------------------------------------------------- #
# Shared column sets (identical in both templates)
# --------------------------------------------------------------------------- #
CRITICITE_SI = ["V", "C", "MC", "PC"]
CRITICITE_FLUX = ["A", "B", "C", "D"]
SENS_FLUX = ["T", "R", "T/R"]

COLS_ACTIVITES = [
    Column("domaine", "Domaine", "Grand domaine fonctionnel de l'entité"),
    Column("processus", "Processus", "Processus métier rattache au domaine"),
    Column("macro_activite", "Macro activite", "Activite operationnelle concrete"),
]

COLS_CONTRAINTES = [
    Column("domaine", "Domaine"),
    Column("processus", "Processus"),
    Column(
        "contraintes",
        "Contraintes operationnelles",
        "Exigences réglementaires, juridiques, contractuelles ou de confidentialite",
    ),
    Column(
        "periodes",
        "Periodes critiques",
        "Périodes de forte activité ou a forts enjeux (clôture mensuelle / annuelle, debut de mois)",
    ),
]

COLS_APPLICATIONS = [
    Column("domaine", "Domaine"),
    Column("processus", "Processus"),
    Column("applications", "Inventaire des applications", "Nom des applications utilisées"),
    Column("couverture", "Couverture fonctionnelle", "Ce que l'application couvre reellement"),
    Column("criticite", "Criticite SI", "Niveau de dépendance", choices=CRITICITE_SI),
]

COLS_FLUX_INTERNES = [
    Column("correspondant", "Groupes fonctionnels / Correspondants"),
    Column("type_info", "Type d'information internes"),
    Column("criticite", "Niveau de criticité", "A, B, C ou D", choices=CRITICITE_FLUX),
    Column("sens", "Transmis / Recu (T/R)", choices=SENS_FLUX),
    Column("ressources", "Ressources SI utilisees"),
]

COLS_FLUX_EXTERNES = [
    Column("correspondant", "Groupes fonctionnels / Correspondants"),
    Column("type_info", "Type d'information externes"),
    Column(
        "typologie",
        "Typologie de correspondants (Mono / Multi)",
        "Mono-correspondant (preciser si monopole) ou Multi-correspondants",
        choices=["Mono", "Mono (monopole)", "Multi"],
    ),
    Column("sens", "Transmis / Recu (T/R)", choices=SENS_FLUX),
    Column("ressources", "Ressources SI utilisees"),
]

COLS_COLLABORATEURS = [
    Column("fonction", "Fonction"),
    Column("nom", "Nom"),
    Column("prenom", "Prenom"),
    Column("poste", "Poste"),
    Column("anciennete", "Ancienneté dans le poste"),
    Column("suppleants", "Suppleants possibles", required=False),
]

COLS_APPLI_ANNEXE = [
    Column("domaine", "Domaine"),
    Column("processus", "Processus"),
    Column("applications", "Inventaire des applications"),
    Column("criticite", "Criticité SI (par application)", choices=CRITICITE_SI),
    Column("contournement", "Contournement envisageable", "Mode dégradé possible sans l'application"),
]

COLS_DOCUMENTS = [
    Column("document", "Documents / Fichiers"),
    Column(
        "stockage",
        "Type de stockage",
        choices=["Electronique", "Papier", "Electronique et Papier"],
    ),
    Column("duplication", "Duplication (O/N) - si oui, ou ?", "Répondre O ou N puis préciser le lieu"),
]


# --------------------------------------------------------------------------- #
# Fiche de suivi (table 1 in both templates)
# --------------------------------------------------------------------------- #
def _fiche(prefix: str) -> List[Question]:
    return [
        Question(
            id=f"{prefix}.fiche.responsable",
            kind="field",
            section="Fiche de suivi",
            label="Nom du Responsable",
            prompt="Pour commencer, quel est le nom du responsable de l'entité ?",
            help="Le responsable hiérarchique de la structure documentee.",
            example="M. Fabrice HAUHOUOT",
            target=Target(table=1, row=2, col=1),
        ),
        # The "Vis-a-vis" cell (table 1, row 3) is deliberately NOT asked here:
        # the consultant fills it by hand after the workshop. Because no question
        # targets it, the filler never touches it and it stays exactly as the
        # template shipped it - blank.
    ]


# --------------------------------------------------------------------------- #
# Annexes (identical structure in both templates, different table offsets)
# --------------------------------------------------------------------------- #
def _annexes(prefix: str, t_int: int, t_ext: int, t_collab: int, t_appli: int, t_docs: int) -> List[Question]:
    return [
        Question(
            id=f"{prefix}.annexe.flux_internes",
            kind="grid",
            section="Annexe - Echanges d'informations internes",
            label="Echanges d'informations internes",
            prompt=(
                "Passons à l'annexe des échanges internes. Avec quelles entités de la banque "
                "echangez-vous des informations, et pour chacune : quel type d'information, "
                "quel niveau de criticité (A a D), le sens du flux (T/R) et les ressources SI utilisées ?"
            ),
            help=(
                "Niveau de criticité du flux - A : ne peut pas être traité manuellement (SI indispensable) ; "
                "B : traitable manuellement de facon limitée dans le temps ; C : traitable manuellement ; "
                "D : peut etre arrete."
            ),
            example="Direction des Engagements | Dossiers de crédit | A | T/R | Core Banking, Messagerie",
            columns=COLS_FLUX_INTERNES,
            target=Target(table=t_int, mode="rows"),
            min_rows=2,
        ),
        Question(
            id=f"{prefix}.annexe.flux_externes",
            kind="grid",
            section="Annexe - Echanges d'informations externes",
            label="Echanges d'informations externes",
            prompt=(
                "Même exercice pour l'exterieur de la banque : quels correspondants externes, "
                "quel type d'information, la typologie (mono ou multi-correspondant), le sens du flux "
                "et les ressources SI utilisées ?"
            ),
            help=(
                "Typologie - Mono-correspondant (préciser s'il est en situation de monopole) "
                "ou Multi-correspondants."
            ),
            example="Banque Centrale de Tunisie | Reporting réglementaire | Mono (monopole) | T | Portail BCT",
            columns=COLS_FLUX_EXTERNES,
            target=Target(table=t_ext, mode="rows"),
        ),
        Question(
            id=f"{prefix}.annexe.collaborateurs",
            kind="grid",
            section="Annexe - Collaborateurs cles",
            label="Collaborateurs cles",
            prompt=(
                "Qui sont vos collaborateurs clés ? Pour chacun : fonction, nom, prénom, poste, "
                "ancienneté dans le poste et suppléants possibles."
            ),
            help=(
                "Est collaborateur clé : tout collaborateur disposant d'une expertise rare ou pointue ; "
                "tout collaborateur qui assure une tache tout seul ; tout collaborateur dont le potentiel "
                "d'encadrement est affirme au sein de l'équipe."
            ),
            example="Expert monetique | Trabelsi | Karim | Ingenieur systeme | 8 ans | Aucun suppleant identifie",
            columns=COLS_COLLABORATEURS,
            target=Target(table=t_collab, mode="rows"),
        ),
        Question(
            id=f"{prefix}.annexe.applications",
            kind="grid",
            section="Annexe - Applications informatiques",
            label="Applications informatiques",
            prompt=(
                "Detaillons l'annexe applicative : pour chaque application, le domaine, le processus, "
                "la criticité SI (V, C, MC ou PC) et le contournement envisageable en cas d'indisponibilité."
            ),
            help=(
                "Criticité SI - Vitale (V) : le processus métier est arrêté si l'application est indisponible ; "
                "Critique (C) : le processus nécessite un travail manuel pour contourner l'application ; "
                "Moyennement critique (MC) : le processus nécessite un contournement par une autre application ; "
                "Peu critique (PC) : le processus reste opérationnel et peu impacté."
            ),
            example="Crédit | Octroi de crédit | Delta Crédit | V | Saisie manuelle sur formulaire papier, 48h max",
            columns=COLS_APPLI_ANNEXE,
            target=Target(table=t_appli, mode="rows"),
        ),
        Question(
            id=f"{prefix}.annexe.documents",
            kind="grid",
            section="Annexe - Documents et fichiers critiques",
            label="Documents et fichiers critiques",
            prompt=(
                "Dernière annexe : quels documents et fichiers critiques utilisez-vous ? "
                "Precisez pour chacun le type de stockage (electronique ou papier) et s'il existe "
                "une duplication, et si oui ou elle se trouve."
            ),
            help="Fichiers, registres et contrats nécessaires à la poursuite de l'activité.",
            example="Registre des garanties | Electronique et Papier | O - coffre agence centrale + GED",
            columns=COLS_DOCUMENTS,
            target=Target(table=t_docs, mode="rows"),
        ),
    ]


# --------------------------------------------------------------------------- #
# Plan: Direction des Systemes d'Information
# --------------------------------------------------------------------------- #
DSI_PLAN: List[Question] = [
    *_fiche("dsi"),
    # --- 2. Organisation, gouvernance & effectifs (table 2) -----------------
    Question(
        id="dsi.organisation.organigramme",
        kind="open",
        section="2. Organisation, gouvernance & effectifs",
        label="Organigramme & Repartition",
        prompt=(
            "Décrivez l'organisation de la DSI : effectif total, répartition par équipe "
            "et rôles détaillés."
        ),
        help="Une réponse rédigée, aussi precise que possible sur les effectifs par équipe.",
        example=(
            "42 collaborateurs repartis en 4 poles : Etudes & Developpement (16), Production & "
            "Infrastructure (12), Securite SI (5), Support & Proximite (9)."
        ),
        target=Target(table=2, row=1, col=1),
    ),
    Question(
        id="dsi.organisation.gouvernance",
        kind="open",
        section="2. Organisation, gouvernance & effectifs",
        label="Gouvernance",
        prompt="Quels comités existent, et comment le pilotage et les décisions sont-ils organisés ?",
        example="Comité SI mensuel preside par le DGA, COPIL projets bimensuel, CAB hebdomadaire.",
        target=Target(table=2, row=2, col=1),
    ),
    # --- 3. Activites et processus metiers (table 3) -------------------------
    Question(
        id="dsi.activites.grid",
        kind="grid",
        section="3. Activités et processus métiers",
        label="Activités et processus métiers",
        prompt=(
            "Cartographions vos activités. Pour chaque domaine, quels sont les processus "
            "et les macro-activités associées ?"
        ),
        example="Production informatique | Exploitation | Supervision des traitements batch de nuit",
        columns=COLS_ACTIVITES,
        target=Target(table=3, mode="rows"),
        min_rows=2,
    ),
    # --- 4. Contraintes operationnelles (table 4) ---------------------------
    Question(
        id="dsi.contraintes.grid",
        kind="grid",
        section="4. Contraintes opérationnelles et périodes critiques",
        label="Contraintes opérationnelles et périodes critiques",
        prompt=(
            "Pour ces mêmes processus, quelles contraintes opérationnelles s'appliquent "
            "et quelles sont les périodes critiques ?"
        ),
        help=(
            "Contraintes operationnelles : exigences reglementaires, juridiques, contractuelles "
            "ou de confidentialite. Périodes critiques : périodes de forte activité ou a forts "
            "enjeux (clôture mensuelle / annuelle, debut de mois)."
        ),
        example="Production | Exploitation | Reporting BCT sous 48h | Cloture mensuelle J+1 a J+3",
        columns=COLS_CONTRAINTES,
        target=Target(table=4, mode="rows"),
    ),
    # --- 5. Architecture SI et Data (table 5) -------------------------------
    Question(
        id="dsi.architecture.si",
        kind="open",
        section="5. Architecture SI et Data",
        label="Architecture SI",
        prompt=(
            "Décrivez votre architecture SI : cartographie applicative et technique, "
            "urbanisation et flux d'integration."
        ),
        example="Core Banking Delta sur AIX, ESB Talend pour les flux, 3 zones réseau segmentees.",
        target=Target(table=5, row=1, col=1),
    ),
    Question(
        id="dsi.architecture.data",
        kind="open",
        section="5. Architecture SI et Data",
        label="Architecture Data",
        prompt="Et cote données : disposez-vous d'un datawarehouse, d'un datalake, d'outils decisionnels ?",
        example="Datawarehouse Oracle alimente en batch quotidien, restitution Power BI.",
        target=Target(table=5, row=2, col=1),
    ),
    # --- 6. Applications & couverture fonctionnelle (table 6) ---------------
    Question(
        id="dsi.applications.grid",
        kind="grid",
        section="6. Applications & couverture fonctionnelle de la DSI",
        label="Applications & couverture fonctionnelle",
        prompt=(
            "Inventorions les applications : par domaine et processus, quelles applications, "
            "quelle couverture fonctionnelle et quelle criticité SI (V, C, MC, PC) ?"
        ),
        help=(
            "Criticite SI - Vitale (V), Critique (C), Moyennement critique (MC), Peu critique (PC). "
            "Elle traduit le niveau de dépendance du processus à l'application."
        ),
        example="Monétique | Gestion des cartes | SAB Monétique | Emission et opposition cartes | V",
        columns=COLS_APPLICATIONS,
        target=Target(table=6, mode="rows"),
    ),
    # --- 7. Infra & strategie Cloud (table 7) -------------------------------
    Question(
        id="dsi.infra.cloud",
        kind="open",
        section="7. Infra & strategie Cloud",
        label="Infra & strategie Cloud",
        prompt=(
            "Faisons l'État des lieux de l'infrastructure : serveurs, hébergement "
            "(On-Premise / Cloud) et stratégie d'infogerance."
        ),
        example="120 VM VMware on-premise sur 2 datacenters actif/passif, aucun IaaS public à ce jour.",
        target=Target(table=7, row=1, col=1),
    ),
    # --- 8. Gestion des donnees & patrimoine documentaire (table 8) ---------
    Question(
        id="dsi.donnees.data",
        kind="open",
        section="8. Gestion des données & patrimoine documentaire",
        label="Donnees manipulees",
        prompt=(
            "Quelles sont les données clés produites ou consommees par la DSI ? "
            "Precisez la sensibilité, la volumétrie et la qualité."
        ),
        example="Données clients (PII) 1,2 M enregistrements, données de transaction 4 M/mois.",
        target=Target(table=8, row=1, col=1),
    ),
    Question(
        id="dsi.donnees.documents",
        kind="open",
        section="8. Gestion des données & patrimoine documentaire",
        label="Liste des documents critiques",
        prompt=(
            "Quels fichiers, registres ou contrats sont nécessaires à l'activité ? "
            "Indiquez le format (papier / electronique) et la localisation."
        ),
        help="Le détail ligne a ligne sera repris dans l'annexe Documents et fichiers critiques.",
        example="Contrats editeurs (electronique, GED juridique), registre des habilitations (electronique).",
        target=Target(table=8, row=2, col=1),
    ),
    # --- 9. Projets et budget SI (table 9) ----------------------------------
    Question(
        id="dsi.projets.portefeuille",
        kind="open",
        section="9. Projets et budget SI",
        label="Portefeuille de projets",
        prompt="Quels sont les projets SI en cours et a venir, et quelle est la feuille de route IT ?",
        example="Refonte du canal digital (2026), migration core banking (2027), PCA/PRA (en cours).",
        target=Target(table=9, row=1, col=1),
    ),
    Question(
        id="dsi.projets.gouvernance",
        kind="open",
        section="9. Projets et budget SI",
        label="Gouvernance des projets SI",
        prompt="Quelle methode de gestion de projet appliquez-vous ?",
        example="Cycle en V pour le coeur bancaire, Scrum pour le digital, PMO central.",
        target=Target(table=9, row=2, col=1),
    ),
    Question(
        id="dsi.projets.budget",
        kind="open",
        section="9. Projets et budget SI",
        label="Budget & Couts IT",
        prompt=(
            "Comment se structure le budget IT (CAPEX / OPEX), et quels sont les coûts "
            "de maintenance et d'infrastructure ?"
        ),
        example="Budget 2026 : 12 MTND dont 60% OPEX ; maintenance editeurs 2,4 MTND.",
        target=Target(table=9, row=3, col=1),
    ),
    # --- 10. Ecosysteme, partenaires & collaborateurs cles (table 10) -------
    Question(
        id="dsi.ecosysteme.correspondants",
        kind="open",
        section="10. Ecosysteme, partenaires & collaborateurs cles",
        label="Correspondants internes / externes",
        prompt=(
            "Quelles sont vos interactions clés, internes et externes ? Precisez le type de flux, "
            "les interdependances, le sens des flux et les canaux utilisés."
        ),
        help="Le détail ligne a ligne sera repris dans les annexes Échanges d'informations.",
        example="Toutes directions métier en interne ; BCT, SIBTEL et editeurs en externe.",
        target=Target(table=10, row=1, col=1),
    ),
    Question(
        id="dsi.ecosysteme.fournisseurs",
        kind="open",
        section="10. Ecosysteme, partenaires & collaborateurs cles",
        label="Fournisseurs & Contrats",
        prompt=(
            "Quels sont vos editeurs et prestataires strategiques, et comment gerez-vous "
            "les SLA et les contrats de maintenance ?"
        ),
        example="SAB (core banking, SLA 4h), Orange Business (MPLS, SLA 99,9%), Devoteam (conseil).",
        target=Target(table=10, row=2, col=1),
    ),
    Question(
        id="dsi.ecosysteme.collaborateurs",
        kind="open",
        section="10. Ecosysteme, partenaires & collaborateurs cles",
        label="Collaborateurs cles & metiers d'expertise",
        prompt="Quels profils presentent une expertise rare ou n'ont pas de binome identifié ?",
        help="Le détail nominatif sera repris dans l'annexe Collaborateurs clés.",
        example="Un seul expert AIX, un seul administrateur monétique.",
        target=Target(table=10, row=3, col=1),
    ),
    # --- 11. Risques IT et historique des incidents (table 11) --------------
    Question(
        id="dsi.risques.it",
        kind="open",
        section="11. Risques IT et historique des incidents",
        label="Risques IT & Securite",
        prompt=(
            "Quels risques cyber avez-vous identifiés ? Qu'en est-il de l'obsolescence technique, "
            "des sauvegardes et du plan de secours informatique (PSI) ?"
        ),
        example=(
            "Ransomware et phishing en tete ; 15% du parc serveur en fin de support ; "
            "sauvegardes quotidiennes externalisées ; PSI teste une fois par an."
        ),
        target=Target(table=11, row=1, col=1),
    ),
    Question(
        id="dsi.risques.incidents",
        kind="open",
        section="11. Risques IT et historique des incidents",
        label="Historique des incidents majeurs",
        prompt=(
            "Quels incidents majeurs ont impacté la continuité d'activité de l'entité ? "
            "Precisez la date, la durée et l'impact."
        ),
        example="Mars 2025 : coupure SAN, 6h d'indisponibilité du core banking, agences en mode dégradé.",
        target=Target(table=11, row=2, col=1),
    ),
    # --- 12. Recueil des besoins (table 12) ---------------------------------
    Question(
        id="dsi.besoins.evolution",
        kind="open",
        section="12. Recueil des besoins & axes d'amelioration",
        label="Besoins d'evolution SI",
        prompt=(
            "Quelles nouvelles fonctionnalites attendez-vous ? Quels besoins en automatisation "
            "et en reporting / analytics ?"
        ),
        example="Automatisation du provisioning, portail self-service, reporting temps reel.",
        target=Target(table=12, row=1, col=1),
    ),
    *_annexes("dsi", t_int=13, t_ext=14, t_collab=15, t_appli=16, t_docs=17),
]


# --------------------------------------------------------------------------- #
# Plan: entite metier
# --------------------------------------------------------------------------- #
ENTITE_PLAN: List[Question] = [
    *_fiche("ent"),
    Question(
        id="ent.organisation.organigramme",
        kind="open",
        section="2. Organisation, gouvernance & effectifs",
        label="Organigramme & Repartition",
        prompt=(
            "Décrivez l'organisation de votre entité : effectif total, répartition par "
            "pôle ou équipe, et rôles clés."
        ),
        example="18 collaborateurs : 1 directeur, 3 chefs de service, 14 gestionnaires.",
        target=Target(table=2, row=1, col=1),
    ),
    Question(
        id="ent.organisation.gouvernance",
        kind="open",
        section="2. Organisation, gouvernance & effectifs",
        label="Gouvernance",
        prompt="Quels comités existent, et comment le pilotage et les décisions sont-ils organisés ?",
        example="Comité hebdomadaire de service, reporting mensuel au COMEX.",
        target=Target(table=2, row=2, col=1),
    ),
    Question(
        id="ent.activites.grid",
        kind="grid",
        section="3. Activités et processus métiers",
        label="Activités et processus métiers",
        prompt=(
            "Cartographions vos activités. Pour chaque domaine, quels sont les processus "
            "et les macro-activités associées ?"
        ),
        example="Crédit | Octroi | Analyse et instruction des dossiers de crédit",
        columns=COLS_ACTIVITES,
        target=Target(table=3, mode="rows"),
        min_rows=2,
    ),
    Question(
        id="ent.contraintes.grid",
        kind="grid",
        section="4. Contraintes opérationnelles et périodes critiques",
        label="Contraintes opérationnelles et périodes critiques",
        prompt=(
            "Pour ces mêmes processus, quelles contraintes opérationnelles s'appliquent "
            "et quelles sont les périodes critiques ?"
        ),
        help=(
            "Contraintes operationnelles : exigences reglementaires, juridiques, contractuelles "
            "ou de confidentialite. Périodes critiques : périodes de forte activité ou a forts "
            "enjeux (clôture mensuelle / annuelle, debut de mois)."
        ),
        example="Crédit | Octroi | Délai réglementaire de réponse 15 jours | Fin de trimestre",
        columns=COLS_CONTRAINTES,
        target=Target(table=4, mode="rows"),
    ),
    Question(
        id="ent.applications.grid",
        kind="grid",
        section="5. Applications & couverture fonctionnelle",
        label="Applications & couverture fonctionnelle",
        prompt=(
            "Quelles applications utilisez-vous ? Pour chacune : domaine, processus, "
            "couverture fonctionnelle et criticité SI (V, C, MC, PC)."
        ),
        help=(
            "Criticite SI - Vitale (V), Critique (C), Moyennement critique (MC), Peu critique (PC)."
        ),
        example="Crédit | Octroi | Delta Crédit | Instruction et deblocage | V",
        columns=COLS_APPLICATIONS,
        target=Target(table=5, mode="rows"),
    ),
    Question(
        id="ent.donnees.data",
        kind="open",
        section="6. Gestion des données & patrimoine documentaire",
        label="Donnees manipulees",
        prompt=(
            "Quelles données clés produisez-vous ou consommez-vous ? Precisez la sensibilité, "
            "la volumétrie et la qualité."
        ),
        example="Dossiers clients avec pieces d'identité, environ 300 nouveaux dossiers par mois.",
        target=Target(table=6, row=1, col=1),
    ),
    Question(
        id="ent.donnees.documents",
        kind="open",
        section="6. Gestion des données & patrimoine documentaire",
        label="Liste des documents critiques",
        prompt=(
            "Quels fichiers, registres ou contrats sont nécessaires à votre activité ? "
            "Indiquez le format (papier / electronique) et la localisation."
        ),
        help="Le détail ligne a ligne sera repris dans l'annexe Documents et fichiers critiques.",
        example="Dossiers de garantie papier en archive, échéanciers dans la GED.",
        target=Target(table=6, row=2, col=1),
    ),
    Question(
        id="ent.ecosysteme.correspondants",
        kind="open",
        section="7. Ecosysteme, partenaires & collaborateurs cles",
        label="Correspondants internes / externes",
        prompt=(
            "Quelles sont vos interactions clés, internes et externes ? Precisez le type de flux, "
            "les interdependances, le sens des flux et les canaux utilisés."
        ),
        help="Le détail ligne a ligne sera repris dans les annexes Échanges d'informations.",
        example="Agences et Direction des Risques en interne ; notaires et huissiers en externe.",
        target=Target(table=7, row=1, col=1),
    ),
    Question(
        id="ent.ecosysteme.collaborateurs",
        kind="open",
        section="7. Ecosysteme, partenaires & collaborateurs cles",
        label="Collaborateurs cles & metiers d'expertise",
        prompt="Quels profils presentent une expertise rare ou n'ont pas de binome identifié ?",
        help="Le détail nominatif sera repris dans l'annexe Collaborateurs clés.",
        example="Un seul juriste specialise en recouvrement contentieux.",
        target=Target(table=7, row=2, col=1),
    ),
    Question(
        id="ent.incidents.historique",
        kind="open",
        section="8. Historique des incidents",
        label="Historique des incidents majeurs",
        prompt=(
            "Quels incidents majeurs ont impacté la continuité de votre activité ? "
            "Precisez la date, la durée et l'impact."
        ),
        example="Janvier 2026 : indisponibilite GED pendant 2 jours, instruction ralentie.",
        target=Target(table=8, row=1, col=1),
    ),
    Question(
        id="ent.besoins.evolution",
        kind="open",
        section="9. Recueil des besoins & axes d'amelioration",
        label="Besoins d'evolution SI",
        prompt=(
            "Quelles nouvelles fonctionnalites attendez-vous ? Quels besoins en automatisation "
            "et en reporting / analytics ?"
        ),
        example="Signature electronique des contrats, tableau de bord d'encours temps reel.",
        target=Target(table=9, row=1, col=1),
    ),
    Question(
        id="ent.besoins.projets",
        kind="open",
        section="9. Recueil des besoins & axes d'amelioration",
        label="Projets a venir",
        prompt=(
            "Quelles initiatives métier sont planifiees a court ou moyen terme "
            "avec un impact sur le SI ?"
        ),
        example="Lancement d'une offre de crédit en ligne au S2 2026.",
        target=Target(table=9, row=2, col=1),
    ),
    *_annexes("ent", t_int=10, t_ext=11, t_collab=12, t_appli=13, t_docs=14),
]


PLANS: Dict[str, List[Question]] = {"dsi": DSI_PLAN, "entite": ENTITE_PLAN}

TEMPLATE_FILES: Dict[str, str] = {
    "dsi": "etat_des_lieux_dsi.docx",
    "entite": "etat_des_lieux_entite.docx",
}

# Fiche de suivi rows that the platform fills without asking the user.
AUTO_FICHE_ROWS = {
    "date": 0,
    "entite": 1,
    "redacteur": 4,
    "version": 5,
    "reference": 6,
}


def get_plan(template_kind: str) -> List[Question]:
    try:
        return PLANS[template_kind]
    except KeyError as exc:
        raise ValueError(f"unknown template kind: {template_kind!r}") from exc


def question_by_id(template_kind: str, question_id: str) -> Optional[Question]:
    return next((q for q in get_plan(template_kind) if q.id == question_id), None)


def sections(template_kind: str) -> List[str]:
    """Ordered, de-duplicated section titles - drives the progress rail in the UI."""
    seen: List[str] = []
    for q in get_plan(template_kind):
        if q.section not in seen:
            seen.append(q.section)
    return seen
