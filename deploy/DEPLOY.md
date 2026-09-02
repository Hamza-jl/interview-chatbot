# Installer sur un portable qui fait serveur

Quatre conteneurs, une commande, aucune dépendance à Internet une fois
l'installation faite : l'inférence tourne sur la machine, et rien de ce que
saisit un correspondant n'en sort.

```
  navigateur  ──►  web (nginx :8080)  ──►  api (FastAPI)  ──►  db (Postgres)
   du réseau          sert le front         │
                      relaie /api           └──►  ollama (qwen2.5:3b)
```

---

## Avant de commencer

Sur le portable-serveur :

- **Docker Desktop** — https://www.docker.com/products/docker-desktop/
- **~12 Go de disque** : images (1,5 Go) + modèle (2 Go) + marge
- **8 Go de RAM minimum**, 16 Go confortable
- Une **IP fixe sur le réseau local**, ou une réservation DHCP. Les
  correspondants taperont cette adresse ; si elle change, ils perdent l'accès.

Relevez l'adresse maintenant, vous en aurez besoin à l'étape 3 :

```powershell
ipconfig | Select-String "IPv4"
```

---

## 1. Transférer les fichiers

Copiez **tout le dossier `mansa-pca-collect`** sur le portable-serveur (clé USB,
partage réseau, ou `git clone` si la machine a accès au dépôt).

Deux dossiers ne sont **pas** dans le dépôt et doivent être copiés à la main
depuis votre machine :

| Chemin | Contenu | Sans lui |
|---|---|---|
| `backend/templates/*.docx` | les deux modèles Word du client | **la construction de l'image échoue** |
| `backend/.env` | ne le copiez **pas** — vous en créerez un neuf | — |

Ce qui n'a pas besoin d'être copié : `backend/var/` (base et exports de votre
poste), `node_modules/`, `__pycache__/`, `.venv/`. Si vous copiez le dossier
entier, supprimez-les sur le serveur — ils seraient inutiles et volumineux.

Vérifiez les modèles avant d'aller plus loin :

```powershell
dir backend\templates\*.docx
```

Deux fichiers doivent apparaître. Sinon, arrêtez-vous ici et récupérez-les.

---

## 2. Générer les secrets

Depuis la racine du projet, sur le serveur :

```powershell
python deploy\generate_keys.py
```

Quatre lignes s'affichent. **Copiez-les**, elles ne seront plus jamais montrées.

> `MASTER_KEK` déchiffre toutes les réponses. Sauvegardez-la **hors de cette
> machine** — dans un gestionnaire de mots de passe, pas dans un fichier à côté.
> La perdre rend les données définitivement illisibles ; la régénérer sur un
> déploiement en service produit le même résultat.

---

## 3. Écrire le fichier .env

```powershell
copy deploy\.env.example .env
notepad .env
```

Collez les quatre secrets, puis renseignez au minimum :

```ini
HTTP_PORT=8080
CORS_ORIGINS=http://192.168.1.50:8080     # ← l'IP relevée, avec le port
COOKIE_SECURE=false

CLIENT_NAME=MANSA Bank
PROGRAMME_LABEL=les projets SDSI et SMCA
CONSULTING_ORG=Devoteam
CONTACT_NAME=Devoteam Tunisie
CONTACT_EMAIL=zouheir.belkahia@devoteam.com
```

`CORS_ORIGINS` doit correspondre **exactement** à ce que les correspondants
tapent, port compris. Une erreur ici donne une page qui s'affiche mais dont la
connexion échoue.

### Pourquoi `COOKIE_SECURE=false`

Le jeton de rafraîchissement voyage dans un cookie. Un cookie `Secure` n'est
jamais renvoyé sur `http://` — la session ne tiendrait pas une minute. En HTTP
simple sur un réseau local, il faut donc `false`.

C'est un vrai compromis : sur le réseau local, le trafic n'est pas chiffré.
Acceptable sur un LAN d'entreprise maîtrisé ; à corriger dès que le service
sort de ce cadre. Avec du TLS devant (reverse proxy, certificat interne),
repassez à `true`.

---

## 4. Démarrer

```powershell
docker compose up -d --build
```

Le premier lancement prend **10 à 20 minutes** : construction des images, puis
téléchargement du modèle (~2 Go). Les suivants démarrent en quelques secondes.

Suivez l'avancement :

```powershell
docker compose ps
docker compose logs -f ollama-pull
```

Quand `ollama-pull` affiche `modèle prêt` et s'arrête, tout est en place. Les
autres services doivent être `Up`, et `api` `(healthy)`.

---

## 5. Créer les comptes

```powershell
docker compose exec api python -m app.scripts.seed
```

Le catalogue des 32 structures est créé, ainsi que **38 comptes** :

- **32 comptes d'entité** — `acf@…`, `si@…`, un par structure. Chacun ne voit
  **que la sienne** : le catalogue qui lui est servi n'a qu'une entrée, et elle
  est sélectionnée d'office. Plusieurs correspondants peuvent donc répondre en
  même temps, chacun sur son périmètre.
- **6 comptes d'administration** en `@devoteam.com`, qui voient l'avancement de
  toutes les entités.

Les mots de passe **ne s'affichent qu'une fois**. Pour 38 comptes, écrivez-les
dans un fichier plutôt que de les recopier :

```powershell
docker compose exec api python -m app.scripts.seed --credentials-file /srv/var/transcripts/identifiants.csv
```

Le fichier apparaît côté hôte dans `deploy/transcripts/identifiants.csv`, avec
une ligne par compte : entité, code, adresse, mot de passe provisoire.

> Ce fichier contient des **mots de passe en clair**. Il sert à les distribuer,
> puis se supprime. Ne le laissez pas sur le serveur.

À la première connexion, chaque compte doit enrôler une application
d'authentification (TOTP) puis changer son mot de passe.

Relancer `seed` plus tard est sans danger : les comptes et structures existants
sont laissés tels quels, et l'ancien compte partagé
`participant@mansabank.tn` est désactivé s'il existe encore.

---

## 6. Vérifier

Depuis le serveur :

```powershell
curl http://localhost:8080/api/v1/contact
```

La fiche de contact doit revenir en JSON. Puis **depuis un autre poste du
réseau**, ouvrez `http://192.168.1.50:8080` et connectez-vous.

Si la page s'affiche mais que la connexion échoue, c'est presque toujours
`CORS_ORIGINS` qui ne correspond pas à l'URL tapée.

---

## Exploitation courante

| Besoin | Commande |
|---|---|
| État des services | `docker compose ps` |
| Journaux de l'API | `docker compose logs -f api` |
| Redémarrer | `docker compose restart api` |
| Arrêter | `docker compose stop` |
| Arrêter et supprimer les conteneurs | `docker compose down` |
| Mettre à jour le code | `git pull` puis `docker compose up -d --build` |

> `docker compose down -v` supprime **les volumes**, donc la base et toutes les
> réponses. Ne l'utilisez jamais sur le serveur en service.

### Démarrage automatique

Les services sont en `restart: unless-stopped` : ils repartent après un
redémarrage de la machine, à condition que Docker Desktop se lance à
l'ouverture de session. Vérifiez-le dans **Docker Desktop → Settings → General
→ Start Docker Desktop when you sign in**.

Le portable ne doit pas se mettre en veille : **Paramètres → Système →
Alimentation → Veille : Jamais** quand il est branché.

### Sauvegarde

Tout ce qui compte est dans la base :

```powershell
docker compose exec db pg_dump -U pca pca > sauvegarde-2026-09-01.sql
```

Gardez ces fichiers **avec** une copie de `MASTER_KEK` : la sauvegarde est
inutilisable sans elle, puisque les réponses y sont chiffrées.

Restauration :

```powershell
type sauvegarde-2026-09-01.sql | docker compose exec -T db psql -U pca pca
```

---

## Les journaux de conversation

Avec `TRANSCRIPT_ENABLED=true` dans le `.env`, chaque entretien est écrit en
Markdown dans **`deploy/transcripts/`**, un fichier par entité, relu à chaque
échange. Le dossier est monté depuis l'hôte : vous les ouvrez directement, sans
entrer dans un conteneur.

> Ces fichiers sont **en clair**, là où la base chiffre chaque réponse. C'est le
> prix de la lisibilité. Laissez `false` si vous n'en avez pas l'usage.

---

## Produire les documents Word

Le chatbot génère le `.docx` à la clôture de chaque entretien, téléchargeable
depuis l'application.

Pour la collecte par Google Forms, exportez le classeur de réponses puis :

```powershell
docker compose cp "Etat des lieux - Reponses.xlsx" api:/tmp/reponses.xlsx
docker compose exec api python -m app.scripts.from_forms /tmp/reponses.xlsx -o /srv/var/transcripts/sorties
```

Les documents apparaissent dans `deploy/transcripts/sorties/` côté hôte.

---

## En cas de blocage

**`api` reste `unhealthy`** — `docker compose logs api`. Presque toujours une
clé du `.env` de mauvaise longueur ; le message le dit explicitement
(`MASTER_KEK must decode to exactly 32 bytes`). Régénérez avec
`generate_keys.py`.

**Le premier message d'entretien met très longtemps** — le modèle n'est pas
encore chargé. `docker compose logs ollama-pull` confirme le téléchargement.

**Réponses lentes** — normal sans GPU : Ollama tourne ici sur le processeur.
Pour utiliser une carte NVIDIA, installez Ollama directement sur Windows plutôt
qu'en conteneur, retirez les services `ollama` et `ollama-pull` du
`docker-compose.yml`, et pointez l'API dessus :

```yaml
OLLAMA_BASE_URL: http://host.docker.internal:11434
```

**Un poste du réseau n'accède pas au serveur** — le pare-feu Windows bloque le
port. Ouvrez-le :

```powershell
New-NetFirewallRule -DisplayName "Etat des lieux" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
```

**La construction échoue sur `COPY templates`** — les `.docx` du client ne sont
pas sur la machine. Retour à l'étape 1.

---

## Mettre à jour un serveur déjà en service

Cinq commandes, deux minutes, **sans perdre les réponses déjà collectées** : la
base et le modèle vivent dans des volumes, que la reconstruction ne touche pas.

```powershell
cd C:\chemin\vers\mansa-pca-collect

git pull                                  # ou recopiez le dossier à la main
docker compose build api web              # reconstruit les deux images
docker compose up -d api web              # bascule sur les nouvelles
docker compose exec api python -m app.scripts.seed
docker compose ps                         # api doit repasser (healthy)
```

`db` et `ollama` ne sont pas redémarrés : ils n'ont pas changé, et les laisser
tranquilles évite de recharger 2 Go de modèle.

`seed` est à relancer **à chaque mise à jour** : il ajoute les comptes et les
structures manquants sans toucher à l'existant. Les mots de passe des nouveaux
comptes s'affichent une seule fois — notez-les avant de fermer la fenêtre.

> Si vous avez recopié le dossier à la main plutôt que `git pull`, n'oubliez pas
> `backend/templates/*.docx` : ils ne sont pas dans le dépôt, et la
> reconstruction échoue sans eux.

### Vérifier que la mise à jour a pris

```powershell
docker compose exec api python -c "from app.api import admin; print([r.path for r in admin.router.routes])"
```

`/admin/progress` et `/admin/sessions/{session_id}/reset` doivent apparaître.

### Revenir en arrière

Les images précédentes restent sur la machine tant qu'elles ne sont pas
nettoyées :

```powershell
docker images etat-des-lieux-api        # relevez l'IMAGE ID précédent
docker tag <IMAGE_ID> etat-des-lieux-api:latest
docker compose up -d api
```

### Le fichier .env doit rester en place

`docker compose build`, `down`, `ps` — toutes ces commandes lisent le `.env`,
parce que les variables obligatoires sont vérifiées avant même que Compose sache
ce que vous voulez faire :

```
error while interpolating services.api.environment.MASTER_KEK:
required variable MASTER_KEK is missing a value
```

Ne le déplacez pas « le temps de faire une manipulation » : vous ne pourriez
plus arrêter proprement votre propre pile. En dépannage, `docker rm -f` sur les
conteneurs contourne le problème.

---

## Le suivi de la collecte (administrateurs)

Les comptes en `@devoteam.com` ont le rôle **admin**. Après connexion, le menu
du compte (en haut à droite) propose **« Suivi de la collecte »** :

- l'avancement des 32 entités, y compris celles que personne n'a ouvertes ;
- pour chacune : état, points renseignés, points restants, participant, dernière
  activité ;
- un bouton **Réinitialiser** par entretien.

Réinitialiser efface les réponses de l'entité et la ramène à la première
question. C'est le seul moyen de rattraper une entité choisie par erreur, y
compris sur un entretien déjà clôturé — celui-ci se rouvre alors, et l'entité
peut être documentée à nouveau.

L'opération est **irréversible**, demande une confirmation, et est inscrite au
journal d'audit avec le nombre de réponses détruites :

```powershell
docker compose exec api python -c "
import json;from app.db.session import SessionLocal;from sqlalchemy import select
from app.db.models import AuditLog
with SessionLocal() as db:
    for e in db.execute(select(AuditLog).where(AuditLog.action=='admin.session_reset')).scalars():
        print(e.ts, e.actor_id, e.target, e.meta)"
```

Un administrateur voit **des compteurs, jamais des réponses** : l'endpoint qui
alimente cet écran ne déchiffre rien.

---

## Un compte par entité

Il n'y a plus de compte partagé. Chaque structure a le sien, verrouillé sur
elle :

| Entité | Adresse |
|---|---|
| Systèmes d'Information | `si@<domaine>` |
| Audit Comptable et Financier | `acf@<domaine>` |
| … | un par code de structure |

Le domaine se règle dans le `.env` :

```ini
PARTICIPANT_EMAIL_DOMAIN=mansabank.tn
```

Mettez-y le domaine de messagerie réel si ces adresses doivent recevoir du
courrier ; sinon `entites.local` convient, ce sont des identifiants de
connexion, pas des boîtes aux lettres.

L'adresse est dérivée du **code** de la structure, pas du nom d'une personne :
le correspondant d'une entité peut changer sans que le compte bouge.

Le verrouillage est appliqué **côté serveur**, pas seulement masqué dans
l'interface : un compte d'entité qui tenterait d'ouvrir une autre structure
reçoit un 403.

### Migrer un serveur qui tourne déjà avec le compte partagé

```powershell
git pull
docker compose build api web
docker compose up -d api web
docker compose exec api python -m app.scripts.seed --credentials-file /srv/var/transcripts/identifiants.csv
```

Le seed crée les 32 comptes manquants et **désactive** `participant@mansabank.tn`.
Le compte n'est pas supprimé : les entrées du journal d'audit qui le désignent
doivent continuer à pointer vers un utilisateur réel.

Les entretiens déjà ouverts sous le compte partagé **restent sa propriété** et
ne sont plus accessibles une fois celui-ci désactivé. Le nouveau compte d'entité
n'est pas bloqué pour autant : la règle « un entretien par entité » se lit par
utilisateur, donc il repart d'un entretien neuf.

L'ancien entretien subsiste et reste visible dans **Suivi de la collecte** — il
peut donc y avoir deux lignes pour une même entité le temps de la transition.
Si la collecte avait déjà commencé, relevez l'avancement avant de basculer :
rien n'est perdu, mais rien n'est repris automatiquement non plus.
