/**
 * Question plan for the état des lieux forms.
 *
 * GENERATED FILE - do not edit. Regenerate with:
 *   python -m app.scripts.export_forms_spec google-forms/Questions.gs
 * Generated: 2026-08-31T15:37:12+01:00
 */

var SPEC = {
  "generated": "2026-08-31T15:37:12+01:00",
  "note": "Généré depuis app/pca/blueprint.py - ne pas modifier à la main.",
  "plans": {
    "dsi": {
      "label": "Direction des Systèmes d'Information",
      "sections": [
        "Fiche de suivi",
        "2. Organisation, gouvernance & effectifs",
        "3. Activités et processus métiers",
        "4. Contraintes opérationnelles et périodes critiques",
        "5. Architecture SI et Data",
        "6. Applications & couverture fonctionnelle de la DSI",
        "7. Infra & strategie Cloud",
        "8. Gestion des données & patrimoine documentaire",
        "9. Projets et budget SI",
        "10. Écosystème, partenaires & collaborateurs clés",
        "11. Risques IT et historique des incidents",
        "12. Recueil des besoins & axes d'amelioration",
        "Annexe - Echanges d'informations internes",
        "Annexe - Echanges d'informations externes",
        "Annexe - Collaborateurs clés",
        "Annexe - Applications informatiques",
        "Annexe - Documents et fichiers critiques"
      ],
      "questions": [
        {
          "id": "dsi.fiche.responsable",
          "index": 0,
          "kind": "field",
          "section": "Fiche de suivi",
          "label": "Nom du Responsable",
          "prompt": "Pour commencer, quel est le nom du responsable de l'entité ?",
          "help": "Le responsable hiérarchique de la structure documentée.",
          "example": "M. Fabrice HAUHOUOT",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.organisation.organigramme",
          "index": 1,
          "kind": "open",
          "section": "2. Organisation, gouvernance & effectifs",
          "label": "Organigramme & Répartition",
          "prompt": "Décrivez l'organisation de la DSI : effectif total, répartition par équipe et rôles détaillés.",
          "help": "Une réponse rédigée, aussi precise que possible sur les effectifs par équipe.",
          "example": "42 collaborateurs répartis en 4 pôles : Études & Développement (16), Production & Infrastructure (12), Sécurité SI (5), Support & Proximité (9).",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.organisation.gouvernance",
          "index": 2,
          "kind": "open",
          "section": "2. Organisation, gouvernance & effectifs",
          "label": "Gouvernance",
          "prompt": "Quels comités existent, et comment le pilotage et les décisions sont-ils organisés ?",
          "help": "",
          "example": "Comité SI mensuel preside par le DGA, COPIL projets bimensuel, CAB hebdomadaire.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.activites.grid",
          "index": 3,
          "kind": "grid",
          "section": "3. Activités et processus métiers",
          "label": "Activités et processus métiers",
          "prompt": "Cartographions vos activités. Pour chaque domaine, quels sont les processus et les macro-activités associées ?",
          "help": "",
          "example": "Production informatique | Exploitation | Supervision des traitements batch de nuit",
          "optional": false,
          "minRows": 2,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "Grand domaine fonctionnel de l'entité",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "Processus métier rattache au domaine",
              "choices": null,
              "required": true
            },
            {
              "id": "macro_activite",
              "label": "Macro activité",
              "hint": "Activité opérationnelle concrète",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "dsi.contraintes.grid",
          "index": 4,
          "kind": "grid",
          "section": "4. Contraintes opérationnelles et périodes critiques",
          "label": "Contraintes opérationnelles et périodes critiques",
          "prompt": "Pour ces mêmes processus, quelles contraintes opérationnelles s'appliquent et quelles sont les périodes critiques ?",
          "help": "Contraintes opérationnelles : exigences réglementaires, juridiques, contractuelles ou de confidentialite. Périodes critiques : périodes de forte activité ou a forts enjeux (clôture mensuelle / annuelle, debut de mois).",
          "example": "Production | Exploitation | Reporting BCT sous 48h | Cloture mensuelle J+1 a J+3",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "contraintes",
              "label": "Contraintes opérationnelles",
              "hint": "Exigences réglementaires, juridiques, contractuelles ou de confidentialite",
              "choices": null,
              "required": true
            },
            {
              "id": "periodes",
              "label": "Périodes critiques",
              "hint": "Périodes de forte activité ou a forts enjeux (clôture mensuelle / annuelle, debut de mois)",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "dsi.architecture.si",
          "index": 5,
          "kind": "open",
          "section": "5. Architecture SI et Data",
          "label": "Architecture SI",
          "prompt": "Décrivez votre architecture SI : cartographie applicative et technique, urbanisation et flux d'integration.",
          "help": "",
          "example": "Core Banking Delta sur AIX, ESB Talend pour les flux, 3 zones réseau segmentees.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.architecture.data",
          "index": 6,
          "kind": "open",
          "section": "5. Architecture SI et Data",
          "label": "Architecture Data",
          "prompt": "Et cote données : disposez-vous d'un datawarehouse, d'un datalake, d'outils decisionnels ?",
          "help": "",
          "example": "Datawarehouse Oracle alimente en batch quotidien, restitution Power BI.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.applications.grid",
          "index": 7,
          "kind": "grid",
          "section": "6. Applications & couverture fonctionnelle de la DSI",
          "label": "Applications & couverture fonctionnelle",
          "prompt": "Inventorions les applications : par domaine et processus, quelles applications, quelle couverture fonctionnelle et quelle criticité SI (V, C, MC, PC) ?",
          "help": "Criticité SI - Vitale (V), Critique (C), Moyennement critique (MC), Peu critique (PC). Elle traduit le niveau de dépendance du processus à l'application.",
          "example": "Monétique | Gestion des cartes | SAB Monétique | Emission et opposition cartes | V",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "applications",
              "label": "Inventaire des applications",
              "hint": "Nom des applications utilisées",
              "choices": null,
              "required": true
            },
            {
              "id": "couverture",
              "label": "Couverture fonctionnelle",
              "hint": "Ce que l'application couvre reellement",
              "choices": null,
              "required": true
            },
            {
              "id": "criticite",
              "label": "Criticité SI",
              "hint": "Niveau de dépendance",
              "choices": [
                "V",
                "C",
                "MC",
                "PC"
              ],
              "required": true
            }
          ]
        },
        {
          "id": "dsi.infra.cloud",
          "index": 8,
          "kind": "open",
          "section": "7. Infra & strategie Cloud",
          "label": "Infra & strategie Cloud",
          "prompt": "Faisons l'État des lieux de l'infrastructure : serveurs, hébergement (On-Premise / Cloud) et stratégie d'infogerance.",
          "help": "",
          "example": "120 VM VMware on-premise sur 2 datacenters actif/passif, aucun IaaS public à ce jour.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.donnees.data",
          "index": 9,
          "kind": "open",
          "section": "8. Gestion des données & patrimoine documentaire",
          "label": "Données manipulées",
          "prompt": "Quelles sont les données clés produites ou consommees par la DSI ? Precisez la sensibilité, la volumétrie et la qualité.",
          "help": "",
          "example": "Données clients (PII) 1,2 M enregistrements, données de transaction 4 M/mois.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.donnees.documents",
          "index": 10,
          "kind": "open",
          "section": "8. Gestion des données & patrimoine documentaire",
          "label": "Liste des documents critiques",
          "prompt": "Quels fichiers, registres ou contrats sont nécessaires à l'activité ? Indiquez le format (papier / electronique) et la localisation.",
          "help": "Le détail ligne a ligne sera repris dans l'annexe Documents et fichiers critiques.",
          "example": "Contrats editeurs (electronique, GED juridique), registre des habilitations (electronique).",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.projets.portefeuille",
          "index": 11,
          "kind": "open",
          "section": "9. Projets et budget SI",
          "label": "Portefeuille de projets",
          "prompt": "Quels sont les projets SI en cours et a venir, et quelle est la feuille de route IT ?",
          "help": "",
          "example": "Refonte du canal digital (2026), migration core banking (2027), PCA/PRA (en cours).",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.projets.gouvernance",
          "index": 12,
          "kind": "open",
          "section": "9. Projets et budget SI",
          "label": "Gouvernance des projets SI",
          "prompt": "Quelle methode de gestion de projet appliquez-vous ?",
          "help": "",
          "example": "Cycle en V pour le coeur bancaire, Scrum pour le digital, PMO central.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.projets.budget",
          "index": 13,
          "kind": "open",
          "section": "9. Projets et budget SI",
          "label": "Budget & Couts IT",
          "prompt": "Comment se structure le budget IT (CAPEX / OPEX), et quels sont les coûts de maintenance et d'infrastructure ?",
          "help": "",
          "example": "Budget 2026 : 12 MTND dont 60% OPEX ; maintenance editeurs 2,4 MTND.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.ecosysteme.correspondants",
          "index": 14,
          "kind": "open",
          "section": "10. Écosystème, partenaires & collaborateurs clés",
          "label": "Correspondants internes / externes",
          "prompt": "Quelles sont vos interactions clés, internes et externes ? Precisez le type de flux, les interdependances, le sens des flux et les canaux utilisés.",
          "help": "Le détail ligne a ligne sera repris dans les annexes Échanges d'informations.",
          "example": "Toutes directions métier en interne ; BCT, SIBTEL et editeurs en externe.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.ecosysteme.fournisseurs",
          "index": 15,
          "kind": "open",
          "section": "10. Écosystème, partenaires & collaborateurs clés",
          "label": "Fournisseurs & Contrats",
          "prompt": "Quels sont vos editeurs et prestataires strategiques, et comment gerez-vous les SLA et les contrats de maintenance ?",
          "help": "",
          "example": "SAB (core banking, SLA 4h), Orange Business (MPLS, SLA 99,9%), Devoteam (conseil).",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.ecosysteme.collaborateurs",
          "index": 16,
          "kind": "open",
          "section": "10. Écosystème, partenaires & collaborateurs clés",
          "label": "Collaborateurs clés & métiers d'expertise",
          "prompt": "Quels profils presentent une expertise rare ou n'ont pas de binome identifié ?",
          "help": "Le détail nominatif sera repris dans l'annexe Collaborateurs clés.",
          "example": "Un seul expert AIX, un seul administrateur monétique.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.risques.it",
          "index": 17,
          "kind": "open",
          "section": "11. Risques IT et historique des incidents",
          "label": "Risques IT & Sécurité",
          "prompt": "Quels risques cyber avez-vous identifiés ? Qu'en est-il de l'obsolescence technique, des sauvegardes et du plan de secours informatique (PSI) ?",
          "help": "",
          "example": "Ransomware et phishing en tete ; 15% du parc serveur en fin de support ; sauvegardes quotidiennes externalisées ; PSI teste une fois par an.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.risques.incidents",
          "index": 18,
          "kind": "open",
          "section": "11. Risques IT et historique des incidents",
          "label": "Historique des incidents majeurs",
          "prompt": "Quels incidents majeurs ont impacté la continuité d'activité de l'entité ? Precisez la date, la durée et l'impact.",
          "help": "",
          "example": "Mars 2025 : coupure SAN, 6h d'indisponibilité du core banking, agences en mode dégradé.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.besoins.evolution",
          "index": 19,
          "kind": "open",
          "section": "12. Recueil des besoins & axes d'amelioration",
          "label": "Besoins d'evolution SI",
          "prompt": "Quelles nouvelles fonctionnalites attendez-vous ? Quels besoins en automatisation et en reporting / analytics ?",
          "help": "",
          "example": "Automatisation du provisioning, portail self-service, reporting temps reel.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "dsi.annexe.flux_internes",
          "index": 20,
          "kind": "grid",
          "section": "Annexe - Echanges d'informations internes",
          "label": "Echanges d'informations internes",
          "prompt": "Passons à l'annexe des échanges internes. Avec quelles entités de la banque echangez-vous des informations, et pour chacune : quel type d'information, quel niveau de criticité (A a D), le sens du flux (T/R) et les ressources SI utilisées ?",
          "help": "Niveau de criticité du flux - A : ne peut pas être traité manuellement (SI indispensable) ; B : traitable manuellement de facon limitée dans le temps ; C : traitable manuellement ; D : peut etre arrete.",
          "example": "Direction des Engagements | Dossiers de crédit | A | T/R | Core Banking, Messagerie",
          "optional": false,
          "minRows": 2,
          "columns": [
            {
              "id": "correspondant",
              "label": "Groupes fonctionnels / Correspondants",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "type_info",
              "label": "Type d'information internes",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "criticite",
              "label": "Niveau de criticité",
              "hint": "A, B, C ou D",
              "choices": [
                "A",
                "B",
                "C",
                "D"
              ],
              "required": true
            },
            {
              "id": "sens",
              "label": "Transmis / Reçu (T/R)",
              "hint": "",
              "choices": [
                "T",
                "R",
                "T/R"
              ],
              "required": true
            },
            {
              "id": "ressources",
              "label": "Ressources SI utilisees",
              "hint": "",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "dsi.annexe.flux_externes",
          "index": 21,
          "kind": "grid",
          "section": "Annexe - Echanges d'informations externes",
          "label": "Echanges d'informations externes",
          "prompt": "Même exercice pour l'exterieur de la banque : quels correspondants externes, quel type d'information, la typologie (mono ou multi-correspondant), le sens du flux et les ressources SI utilisées ?",
          "help": "Typologie - Mono-correspondant (préciser s'il est en situation de monopole) ou Multi-correspondants.",
          "example": "Banque Centrale de Tunisie | Reporting réglementaire | Mono (monopole) | T | Portail BCT",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "correspondant",
              "label": "Groupes fonctionnels / Correspondants",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "type_info",
              "label": "Type d'information externes",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "typologie",
              "label": "Typologie de correspondants (Mono / Multi)",
              "hint": "Mono-correspondant (preciser si monopole) ou Multi-correspondants",
              "choices": [
                "Mono",
                "Mono (monopole)",
                "Multi"
              ],
              "required": true
            },
            {
              "id": "sens",
              "label": "Transmis / Reçu (T/R)",
              "hint": "",
              "choices": [
                "T",
                "R",
                "T/R"
              ],
              "required": true
            },
            {
              "id": "ressources",
              "label": "Ressources SI utilisees",
              "hint": "",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "dsi.annexe.collaborateurs",
          "index": 22,
          "kind": "grid",
          "section": "Annexe - Collaborateurs clés",
          "label": "Collaborateurs clés",
          "prompt": "Qui sont vos collaborateurs clés ? Pour chacun : fonction, nom, prénom, poste, ancienneté dans le poste et suppléants possibles.",
          "help": "Est collaborateur clé : tout collaborateur disposant d'une expertise rare ou pointue ; tout collaborateur qui assure une tache tout seul ; tout collaborateur dont le potentiel d'encadrement est affirme au sein de l'équipe.",
          "example": "Expert monétique | Trabelsi | Karim | Ingénieur système | 8 ans | Aucun suppléant identifié",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "fonction",
              "label": "Fonction",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "nom",
              "label": "Nom",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "prenom",
              "label": "Prénom",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "poste",
              "label": "Poste",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "anciennete",
              "label": "Ancienneté dans le poste",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "suppleants",
              "label": "Suppléants possibles",
              "hint": "",
              "choices": null,
              "required": false
            }
          ]
        },
        {
          "id": "dsi.annexe.applications",
          "index": 23,
          "kind": "grid",
          "section": "Annexe - Applications informatiques",
          "label": "Applications informatiques",
          "prompt": "Detaillons l'annexe applicative : pour chaque application, le domaine, le processus, la criticité SI (V, C, MC ou PC) et le contournement envisageable en cas d'indisponibilité.",
          "help": "Criticité SI - Vitale (V) : le processus métier est arrêté si l'application est indisponible ; Critique (C) : le processus nécessite un travail manuel pour contourner l'application ; Moyennement critique (MC) : le processus nécessite un contournement par une autre application ; Peu critique (PC) : le processus reste opérationnel et peu impacté.",
          "example": "Crédit | Octroi de crédit | Delta Crédit | V | Saisie manuelle sur formulaire papier, 48h max",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "applications",
              "label": "Inventaire des applications",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "criticite",
              "label": "Criticité SI (par application)",
              "hint": "",
              "choices": [
                "V",
                "C",
                "MC",
                "PC"
              ],
              "required": true
            },
            {
              "id": "contournement",
              "label": "Contournement envisageable",
              "hint": "Mode dégradé possible sans l'application",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "dsi.annexe.documents",
          "index": 24,
          "kind": "grid",
          "section": "Annexe - Documents et fichiers critiques",
          "label": "Documents et fichiers critiques",
          "prompt": "Dernière annexe : quels documents et fichiers critiques utilisez-vous ? Precisez pour chacun le type de stockage (electronique ou papier) et s'il existe une duplication, et si oui ou elle se trouve.",
          "help": "Fichiers, registres et contrats nécessaires à la poursuite de l'activité.",
          "example": "Registre des garanties | Electronique et Papier | O - coffre agence centrale + GED",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "document",
              "label": "Documents / Fichiers",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "stockage",
              "label": "Type de stockage",
              "hint": "",
              "choices": [
                "Electronique",
                "Papier",
                "Electronique et Papier"
              ],
              "required": true
            },
            {
              "id": "duplication",
              "label": "Duplication (O/N) - si oui, où ?",
              "hint": "Répondre O ou N puis préciser le lieu",
              "choices": null,
              "required": true
            }
          ]
        }
      ]
    },
    "entite": {
      "label": "Entité",
      "sections": [
        "Fiche de suivi",
        "2. Organisation, gouvernance & effectifs",
        "3. Activités et processus métiers",
        "4. Contraintes opérationnelles et périodes critiques",
        "5. Applications & couverture fonctionnelle",
        "6. Gestion des données & patrimoine documentaire",
        "7. Écosystème, partenaires & collaborateurs clés",
        "8. Historique des incidents",
        "9. Recueil des besoins & axes d'amelioration",
        "Annexe - Echanges d'informations internes",
        "Annexe - Echanges d'informations externes",
        "Annexe - Collaborateurs clés",
        "Annexe - Applications informatiques",
        "Annexe - Documents et fichiers critiques"
      ],
      "questions": [
        {
          "id": "ent.fiche.responsable",
          "index": 0,
          "kind": "field",
          "section": "Fiche de suivi",
          "label": "Nom du Responsable",
          "prompt": "Pour commencer, quel est le nom du responsable de l'entité ?",
          "help": "Le responsable hiérarchique de la structure documentée.",
          "example": "M. Fabrice HAUHOUOT",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.organisation.organigramme",
          "index": 1,
          "kind": "open",
          "section": "2. Organisation, gouvernance & effectifs",
          "label": "Organigramme & Répartition",
          "prompt": "Décrivez l'organisation de votre entité : effectif total, répartition par pôle ou équipe, et rôles clés.",
          "help": "",
          "example": "18 collaborateurs : 1 directeur, 3 chefs de service, 14 gestionnaires.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.organisation.gouvernance",
          "index": 2,
          "kind": "open",
          "section": "2. Organisation, gouvernance & effectifs",
          "label": "Gouvernance",
          "prompt": "Quels comités existent, et comment le pilotage et les décisions sont-ils organisés ?",
          "help": "",
          "example": "Comité hebdomadaire de service, reporting mensuel au COMEX.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.activites.grid",
          "index": 3,
          "kind": "grid",
          "section": "3. Activités et processus métiers",
          "label": "Activités et processus métiers",
          "prompt": "Cartographions vos activités. Pour chaque domaine, quels sont les processus et les macro-activités associées ?",
          "help": "",
          "example": "Crédit | Octroi | Analyse et instruction des dossiers de crédit",
          "optional": false,
          "minRows": 2,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "Grand domaine fonctionnel de l'entité",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "Processus métier rattache au domaine",
              "choices": null,
              "required": true
            },
            {
              "id": "macro_activite",
              "label": "Macro activité",
              "hint": "Activité opérationnelle concrète",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "ent.contraintes.grid",
          "index": 4,
          "kind": "grid",
          "section": "4. Contraintes opérationnelles et périodes critiques",
          "label": "Contraintes opérationnelles et périodes critiques",
          "prompt": "Pour ces mêmes processus, quelles contraintes opérationnelles s'appliquent et quelles sont les périodes critiques ?",
          "help": "Contraintes opérationnelles : exigences réglementaires, juridiques, contractuelles ou de confidentialite. Périodes critiques : périodes de forte activité ou a forts enjeux (clôture mensuelle / annuelle, debut de mois).",
          "example": "Crédit | Octroi | Délai réglementaire de réponse 15 jours | Fin de trimestre",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "contraintes",
              "label": "Contraintes opérationnelles",
              "hint": "Exigences réglementaires, juridiques, contractuelles ou de confidentialite",
              "choices": null,
              "required": true
            },
            {
              "id": "periodes",
              "label": "Périodes critiques",
              "hint": "Périodes de forte activité ou a forts enjeux (clôture mensuelle / annuelle, debut de mois)",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "ent.applications.grid",
          "index": 5,
          "kind": "grid",
          "section": "5. Applications & couverture fonctionnelle",
          "label": "Applications & couverture fonctionnelle",
          "prompt": "Quelles applications utilisez-vous ? Pour chacune : domaine, processus, couverture fonctionnelle et criticité SI (V, C, MC, PC).",
          "help": "Criticité SI - Vitale (V), Critique (C), Moyennement critique (MC), Peu critique (PC).",
          "example": "Crédit | Octroi | Delta Crédit | Instruction et deblocage | V",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "applications",
              "label": "Inventaire des applications",
              "hint": "Nom des applications utilisées",
              "choices": null,
              "required": true
            },
            {
              "id": "couverture",
              "label": "Couverture fonctionnelle",
              "hint": "Ce que l'application couvre reellement",
              "choices": null,
              "required": true
            },
            {
              "id": "criticite",
              "label": "Criticité SI",
              "hint": "Niveau de dépendance",
              "choices": [
                "V",
                "C",
                "MC",
                "PC"
              ],
              "required": true
            }
          ]
        },
        {
          "id": "ent.donnees.data",
          "index": 6,
          "kind": "open",
          "section": "6. Gestion des données & patrimoine documentaire",
          "label": "Données manipulées",
          "prompt": "Quelles données clés produisez-vous ou consommez-vous ? Precisez la sensibilité, la volumétrie et la qualité.",
          "help": "",
          "example": "Dossiers clients avec pieces d'identité, environ 300 nouveaux dossiers par mois.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.donnees.documents",
          "index": 7,
          "kind": "open",
          "section": "6. Gestion des données & patrimoine documentaire",
          "label": "Liste des documents critiques",
          "prompt": "Quels fichiers, registres ou contrats sont nécessaires à votre activité ? Indiquez le format (papier / electronique) et la localisation.",
          "help": "Le détail ligne a ligne sera repris dans l'annexe Documents et fichiers critiques.",
          "example": "Dossiers de garantie papier en archive, échéanciers dans la GED.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.ecosysteme.correspondants",
          "index": 8,
          "kind": "open",
          "section": "7. Écosystème, partenaires & collaborateurs clés",
          "label": "Correspondants internes / externes",
          "prompt": "Quelles sont vos interactions clés, internes et externes ? Precisez le type de flux, les interdependances, le sens des flux et les canaux utilisés.",
          "help": "Le détail ligne a ligne sera repris dans les annexes Échanges d'informations.",
          "example": "Agences et Direction des Risques en interne ; notaires et huissiers en externe.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.ecosysteme.collaborateurs",
          "index": 9,
          "kind": "open",
          "section": "7. Écosystème, partenaires & collaborateurs clés",
          "label": "Collaborateurs clés & métiers d'expertise",
          "prompt": "Quels profils presentent une expertise rare ou n'ont pas de binome identifié ?",
          "help": "Le détail nominatif sera repris dans l'annexe Collaborateurs clés.",
          "example": "Un seul juriste specialise en recouvrement contentieux.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.incidents.historique",
          "index": 10,
          "kind": "open",
          "section": "8. Historique des incidents",
          "label": "Historique des incidents majeurs",
          "prompt": "Quels incidents majeurs ont impacté la continuité de votre activité ? Precisez la date, la durée et l'impact.",
          "help": "",
          "example": "Janvier 2026 : indisponibilite GED pendant 2 jours, instruction ralentie.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.besoins.evolution",
          "index": 11,
          "kind": "open",
          "section": "9. Recueil des besoins & axes d'amelioration",
          "label": "Besoins d'evolution SI",
          "prompt": "Quelles nouvelles fonctionnalites attendez-vous ? Quels besoins en automatisation et en reporting / analytics ?",
          "help": "",
          "example": "Signature electronique des contrats, tableau de bord d'encours temps reel.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.besoins.projets",
          "index": 12,
          "kind": "open",
          "section": "9. Recueil des besoins & axes d'amelioration",
          "label": "Projets a venir",
          "prompt": "Quelles initiatives métier sont planifiees a court ou moyen terme avec un impact sur le SI ?",
          "help": "",
          "example": "Lancement d'une offre de crédit en ligne au S2 2026.",
          "optional": false,
          "minRows": 1,
          "columns": []
        },
        {
          "id": "ent.annexe.flux_internes",
          "index": 13,
          "kind": "grid",
          "section": "Annexe - Echanges d'informations internes",
          "label": "Echanges d'informations internes",
          "prompt": "Passons à l'annexe des échanges internes. Avec quelles entités de la banque echangez-vous des informations, et pour chacune : quel type d'information, quel niveau de criticité (A a D), le sens du flux (T/R) et les ressources SI utilisées ?",
          "help": "Niveau de criticité du flux - A : ne peut pas être traité manuellement (SI indispensable) ; B : traitable manuellement de facon limitée dans le temps ; C : traitable manuellement ; D : peut etre arrete.",
          "example": "Direction des Engagements | Dossiers de crédit | A | T/R | Core Banking, Messagerie",
          "optional": false,
          "minRows": 2,
          "columns": [
            {
              "id": "correspondant",
              "label": "Groupes fonctionnels / Correspondants",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "type_info",
              "label": "Type d'information internes",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "criticite",
              "label": "Niveau de criticité",
              "hint": "A, B, C ou D",
              "choices": [
                "A",
                "B",
                "C",
                "D"
              ],
              "required": true
            },
            {
              "id": "sens",
              "label": "Transmis / Reçu (T/R)",
              "hint": "",
              "choices": [
                "T",
                "R",
                "T/R"
              ],
              "required": true
            },
            {
              "id": "ressources",
              "label": "Ressources SI utilisees",
              "hint": "",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "ent.annexe.flux_externes",
          "index": 14,
          "kind": "grid",
          "section": "Annexe - Echanges d'informations externes",
          "label": "Echanges d'informations externes",
          "prompt": "Même exercice pour l'exterieur de la banque : quels correspondants externes, quel type d'information, la typologie (mono ou multi-correspondant), le sens du flux et les ressources SI utilisées ?",
          "help": "Typologie - Mono-correspondant (préciser s'il est en situation de monopole) ou Multi-correspondants.",
          "example": "Banque Centrale de Tunisie | Reporting réglementaire | Mono (monopole) | T | Portail BCT",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "correspondant",
              "label": "Groupes fonctionnels / Correspondants",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "type_info",
              "label": "Type d'information externes",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "typologie",
              "label": "Typologie de correspondants (Mono / Multi)",
              "hint": "Mono-correspondant (preciser si monopole) ou Multi-correspondants",
              "choices": [
                "Mono",
                "Mono (monopole)",
                "Multi"
              ],
              "required": true
            },
            {
              "id": "sens",
              "label": "Transmis / Reçu (T/R)",
              "hint": "",
              "choices": [
                "T",
                "R",
                "T/R"
              ],
              "required": true
            },
            {
              "id": "ressources",
              "label": "Ressources SI utilisees",
              "hint": "",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "ent.annexe.collaborateurs",
          "index": 15,
          "kind": "grid",
          "section": "Annexe - Collaborateurs clés",
          "label": "Collaborateurs clés",
          "prompt": "Qui sont vos collaborateurs clés ? Pour chacun : fonction, nom, prénom, poste, ancienneté dans le poste et suppléants possibles.",
          "help": "Est collaborateur clé : tout collaborateur disposant d'une expertise rare ou pointue ; tout collaborateur qui assure une tache tout seul ; tout collaborateur dont le potentiel d'encadrement est affirme au sein de l'équipe.",
          "example": "Expert monétique | Trabelsi | Karim | Ingénieur système | 8 ans | Aucun suppléant identifié",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "fonction",
              "label": "Fonction",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "nom",
              "label": "Nom",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "prenom",
              "label": "Prénom",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "poste",
              "label": "Poste",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "anciennete",
              "label": "Ancienneté dans le poste",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "suppleants",
              "label": "Suppléants possibles",
              "hint": "",
              "choices": null,
              "required": false
            }
          ]
        },
        {
          "id": "ent.annexe.applications",
          "index": 16,
          "kind": "grid",
          "section": "Annexe - Applications informatiques",
          "label": "Applications informatiques",
          "prompt": "Detaillons l'annexe applicative : pour chaque application, le domaine, le processus, la criticité SI (V, C, MC ou PC) et le contournement envisageable en cas d'indisponibilité.",
          "help": "Criticité SI - Vitale (V) : le processus métier est arrêté si l'application est indisponible ; Critique (C) : le processus nécessite un travail manuel pour contourner l'application ; Moyennement critique (MC) : le processus nécessite un contournement par une autre application ; Peu critique (PC) : le processus reste opérationnel et peu impacté.",
          "example": "Crédit | Octroi de crédit | Delta Crédit | V | Saisie manuelle sur formulaire papier, 48h max",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "domaine",
              "label": "Domaine",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "processus",
              "label": "Processus",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "applications",
              "label": "Inventaire des applications",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "criticite",
              "label": "Criticité SI (par application)",
              "hint": "",
              "choices": [
                "V",
                "C",
                "MC",
                "PC"
              ],
              "required": true
            },
            {
              "id": "contournement",
              "label": "Contournement envisageable",
              "hint": "Mode dégradé possible sans l'application",
              "choices": null,
              "required": true
            }
          ]
        },
        {
          "id": "ent.annexe.documents",
          "index": 17,
          "kind": "grid",
          "section": "Annexe - Documents et fichiers critiques",
          "label": "Documents et fichiers critiques",
          "prompt": "Dernière annexe : quels documents et fichiers critiques utilisez-vous ? Precisez pour chacun le type de stockage (electronique ou papier) et s'il existe une duplication, et si oui ou elle se trouve.",
          "help": "Fichiers, registres et contrats nécessaires à la poursuite de l'activité.",
          "example": "Registre des garanties | Electronique et Papier | O - coffre agence centrale + GED",
          "optional": false,
          "minRows": 1,
          "columns": [
            {
              "id": "document",
              "label": "Documents / Fichiers",
              "hint": "",
              "choices": null,
              "required": true
            },
            {
              "id": "stockage",
              "label": "Type de stockage",
              "hint": "",
              "choices": [
                "Electronique",
                "Papier",
                "Electronique et Papier"
              ],
              "required": true
            },
            {
              "id": "duplication",
              "label": "Duplication (O/N) - si oui, où ?",
              "hint": "Répondre O ou N puis préciser le lieu",
              "choices": null,
              "required": true
            }
          ]
        }
      ]
    }
  },
  "structures": [
    {
      "code": "SI",
      "name": "Systèmes d'Information",
      "parent": "Transformation & Digital",
      "templateKind": "dsi"
    },
    {
      "code": "ENT",
      "name": "Entreprises & Institutionnels",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "PME",
      "name": "PME & Professionnels",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "CAG",
      "name": "Commodities & Agribusiness",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "CPA",
      "name": "Clientèle Patrimoniale",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "SDM",
      "name": "Salle de Marchés",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "TRD",
      "name": "Trade",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "FST",
      "name": "Financements Structurés",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "ACE",
      "name": "Analyse de Crédit Entreprise",
      "parent": "Banque de Financement",
      "templateKind": "entite"
    },
    {
      "code": "PSD",
      "name": "Produits et Solutions Digitales",
      "parent": "Transformation & Digital",
      "templateKind": "entite"
    },
    {
      "code": "PAD",
      "name": "Partenariats & Distribution",
      "parent": "Transformation & Digital",
      "templateKind": "entite"
    },
    {
      "code": "CMG",
      "name": "Cash Management",
      "parent": "Transformation & Digital",
      "templateKind": "entite"
    },
    {
      "code": "TDA",
      "name": "Transformation Digitale & Data Analytics",
      "parent": "Transformation & Digital",
      "templateKind": "entite"
    },
    {
      "code": "RIS",
      "name": "Gestion des Risques",
      "parent": "Risques & Contrôle",
      "templateKind": "entite"
    },
    {
      "code": "CFT",
      "name": "Conformité",
      "parent": "Risques & Contrôle",
      "templateKind": "entite"
    },
    {
      "code": "SSI",
      "name": "Sécurité Système d'Information",
      "parent": "Risques & Contrôle",
      "templateKind": "entite"
    },
    {
      "code": "ATE",
      "name": "Audit Technologique",
      "parent": "Risques & Contrôle",
      "templateKind": "entite"
    },
    {
      "code": "ACF",
      "name": "Audit Comptable et Financier",
      "parent": "Risques & Contrôle",
      "templateKind": "entite"
    },
    {
      "code": "OPE",
      "name": "Opérations",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "EXC",
      "name": "Expérience Client",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "QUA",
      "name": "Qualité",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "CQP",
      "name": "Crédits et Qualité de Portefeuille",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "ADC",
      "name": "Administration du Crédit",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "AJU",
      "name": "Affaires Juridiques",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "CPR",
      "name": "Comptabilité & Reporting",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "CCO",
      "name": "Contrôle Comptabilité",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "CDG",
      "name": "Contrôle de Gestion",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "SGE",
      "name": "Services Généraux",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "MKC",
      "name": "Marketing & Communication",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "GPR",
      "name": "Gestion Projets",
      "parent": "Opérations & Support",
      "templateKind": "entite"
    },
    {
      "code": "GCH",
      "name": "Gestion administrative Capital Humain",
      "parent": "Capital Humain",
      "templateKind": "entite"
    },
    {
      "code": "DCH",
      "name": "Développement Capital Humain",
      "parent": "Capital Humain",
      "templateKind": "entite"
    }
  ]
};
