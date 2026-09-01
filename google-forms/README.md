# Collecte par Google Forms

**Deux formulaires** posant exactement les mêmes questions que le chatbot, dans
le même ordre. Les réponses redescendent dans le même générateur de document :
les deux canaux produisent le même `.docx`.

| Formulaire | Pour | Points |
|---|---|---|
| **Entités** | les 31 entités — le correspondant choisit la sienne dans une liste déroulante | 18 |
| **DSI** | Systèmes d'Information uniquement | 25 |

```
blueprint.py ──► Questions.gs ──► 2 Google Forms ──► classeur de réponses
   (source)       (généré)          (Code.gs)        (brut + 1 onglet / entité)
                                                                  │
                                                                  ▼
                                                        from_forms.py
                                                                  │
                                                                  ▼
                                                   Etat_des_lieux_<entité>.docx
```

> **Pourquoi deux et non trente-deux.** Un formulaire par entité se routait tout
> seul, mais coûtait 32 créations à ~65 s pièce — au-delà de la limite de
> 6 minutes d'Apps Script, donc six relances manuelles — puis 32 liens à
> diffuser et à régénérer à chaque évolution du plan. Deux formulaires se créent
> en une exécution. En échange, le correspondant choisit son entité lui-même :
> c'est la première question, obligatoire, et c'est elle qui décide du document
> produit.

---

## 1. Créer les formulaires

1. [script.google.com](https://script.google.com) → **Nouveau projet**
2. Créez deux fichiers et collez-y `Code.gs` et `Questions.gs`
3. Exécutez **`setUp()`** — autorisez l'accès au premier lancement
4. Exécutez **`createForms()`** — une seule exécution suffit
5. Exécutez **`listForms()`** → l'onglet **Liens** avec les deux URL à diffuser

| Fonction | Effet |
|---|---|
| `setUp()` | Crée le dossier Drive et le classeur de réponses |
| `createForms()` | Crée les deux formulaires et installe le routage |
| `listForms()` | Écrit l'onglet **Liens** |
| `rebuildStructureSheets()` | Reventile toutes les réponses par entité |
| `deleteAllForms()` | Met les formulaires à la corbeille |

Tout atterrit dans le dossier Drive **Etat des lieux - Formulaires**.

---

## 2. Où arrivent les réponses

Dans un classeur unique, **Etat des lieux - Reponses** :

- **Onglets bruts** — un par formulaire, alimentés par Google. Source de vérité.
- **Onglets par entité** — `ACF - Audit Comptable et Financ`, créés à la
  première réponse par un déclencheur `onFormSubmit`. Une **vue**, pas la
  source : `rebuildStructureSheets()` les reconstruit à tout moment, donc un
  déclencheur manqué ne perd rien.

Le code de l'entité est en tête du nom d'onglet parce que **l'export `.xlsx`
tronque un nom d'onglet à 31 caractères** et couperait le nom en plein milieu.

Chaque ligne : `Horodateur | Adresse e-mail | Structure documentée | ` puis une
colonne par question. Les en-têtes de section ne créent pas de colonne.

---

## 3. Les questions tableau

Google Forms n'a pas de tableau à saisie libre — ses « grilles » sont des
échelles de notation. Une question par cellule donnerait des formulaires de
plusieurs centaines de champs, avec un nombre de lignes figé d'avance.

Ces questions deviennent donc **une question longue, une ligne par entrée,
colonnes séparées par `|`** :

```
Comptabilité | Arrêté mensuel | Accès Sage indisponible | Fin de mois, J+1 à J+5
Trésorerie   | Règlements     | Swift indisponible      | Quotidien, 9h-11h
```

L'intitulé rappelle les colonnes, les valeurs attendues (V/C/MC/PC, A/B/C/D…)
et un exemple. C'est le format que l'application analyse déjà **sans modèle**,
d'où l'identité des deux canaux.

Un tableau saisi sans `|` n'est jamais perdu : chaque ligne va dans la première
colonne, et l'import le signale.

---

## 4. Produire les documents

Depuis le classeur : **Fichier › Télécharger › Microsoft Excel**.

```bash
cd backend
python -m app.scripts.from_forms "Etat des lieux - Reponses.xlsx" -o ./sorties
```

```
  ✓ Audit Comptable et Financier (ACF) — 18/18 points → Etat_des_lieux_Audit_Comptable_et_Financier.docx
  ✓ Systèmes d'Information (SI) — 24/25 points → Etat_des_lieux_Systemes_d_Information.docx
      · 1 point(s) sans réponse : Documents et fichiers critiques
```

| Option | Effet |
|---|---|
| `-o DOSSIER` | Dossier de sortie (défaut `./sorties`) |
| `--all` | Un document par réponse, et non la plus récente seulement |
| `--redacteur "…"` | Mention portée dans la fiche de suivi |

L'entité vient de la colonne **Structure documentée**, pas du nom d'onglet :
c'est la réponse du correspondant qui fait foi. Les onglets par entité
reprenant les lignes brutes, les doublons sont écartés — une réponse, un
document. Par défaut la réponse **la plus récente** de chaque entité l'emporte,
donc un correspondant peut renvoyer le formulaire pour se corriger.

### Pourquoi le document n'est pas produit par Google

Les modèles sont les `.docx` du client, avec des tableaux et des cellules
fusionnées. Un aller-retour par Google Docs ne les préserve pas. Le document
reste produit par `docx_filler`, le code que le chatbot utilise déjà et que les
tests de gabarit couvrent.

---

## 5. Faire évoluer les questions

Le plan a une seule source : `backend/app/pca/blueprint.py`. **Ne modifiez
jamais une question dans `Questions.gs`** — elle serait écrasée, et les deux
canaux divergeraient.

```bash
cd backend
python -m app.scripts.export_forms_spec ../google-forms/Questions.gs
```

Recollez `Questions.gs` dans le projet Apps Script, puis `deleteAllForms()` et
`createForms()`.

> Recréer les formulaires **supprime les réponses déjà collectées**. Exportez le
> classeur avant.

L'intitulé `Structure documentée` est partagé entre `Code.gs`
(`STRUCTURE_QUESTION`) et `from_forms.py` (`STRUCTURE_COLUMN`) : changer l'un
sans l'autre casse l'identification de l'entité.
