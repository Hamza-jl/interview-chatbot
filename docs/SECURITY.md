# Dossier de sécurité

Ce document décrit les contrôles implémentés, la façon de les vérifier, et les
limites connues. Il est destiné aux équipes sécurité et aux auditeurs.

## 1. Modèle de menace

Les données collectées sont des données de continuité d'activité :
cartographie applicative, criticité des processus, incidents majeurs, noms de
collaborateurs clés et de leurs suppléants. Un attaquant qui les obtient dispose
d'une **carte des points de rupture de l'établissement**.

| Menace                                            | Contrôle principal                                   |
| ------------------------------------------------- | ---------------------------------------------------- |
| Vol d'identifiants (phishing, réutilisation)       | TOTP obligatoire, verrouillage, mots de passe Argon2id |
| Vol du cookie de session                           | rotation des jetons + détection de rejeu             |
| Compromission de la base ou d'une sauvegarde       | chiffrement AES-256-GCM par champ, clés hors base    |
| Élévation de privilège / accès inter-entités       | contrôle de propriété au niveau de la requête SQL    |
| XSS / injection dans l'interface                   | aucun rendu HTML brut, CSP stricte                   |
| Injection de consignes via le contenu utilisateur  | modèle sans outil, sortie contrainte par schéma      |
| Falsification a posteriori des traces              | journal d'audit chaîné par hachage                   |
| Exfiltration du livrable                           | document chiffré au repos, lien signé de 2 minutes   |

## 2. Authentification

**Mot de passe** — Argon2id (`time_cost=3`, `memory_cost=64 MiB`, `parallelism=4`).
Le hachage est re-calculé automatiquement si les paramètres évoluent.

**Égalisation temporelle** — une tentative sur un compte inexistant exécute quand
même une vérification Argon2 contre un condensat factice. Le temps de réponse ne
révèle donc pas l'existence d'un compte, et le message d'erreur est strictement
identique dans les deux cas (`Identifiants invalides.`).

**Second facteur** — TOTP (RFC 6238), fenêtre de tolérance ±30 s. Le secret est
chiffré au repos sous la KEK maître. Huit codes de secours à usage unique sont
générés à l'enrôlement et stockés uniquement sous forme de condensats SHA-256.

**Verrouillage** — 5 échecs consécutifs verrouillent le compte 15 minutes. Un
verrouillage déjà actif ne se prolonge pas de lui-même (pas de déni de service
auto-infligé par un attaquant qui persévère).

**Politique de mot de passe** — 12 caractères minimum, quatre classes de
caractères, refus des termes prévisibles du contexte (`continuite`, `password`, …) et refus d'un mot de passe contenant l'identifiant. La politique
est appliquée **côté serveur** ; l'affichage côté client n'est qu'une aide.

## 3. Sessions

| Élément            | Durée   | Stockage                                        |
| ------------------ | ------- | ----------------------------------------------- |
| Jeton d'accès      | 10 min  | mémoire du navigateur uniquement                |
| Jeton de rafraîchissement | 12 h max | cookie `HttpOnly` `Secure` `SameSite=Strict` |
| Inactivité         | 15 min  | vérifiée côté serveur à chaque requête          |

Le jeton d'accès n'est **jamais** placé dans `localStorage` ni `sessionStorage` :
une charge XSS ne peut pas le relire depuis un stockage persistant, et il meurt
avec l'onglet. La longévité vient du cookie de rafraîchissement, que JavaScript
ne peut pas lire du tout.

**Rotation et détection de rejeu** — chaque rafraîchissement consomme le jeton
courant et en émet un nouveau. Si un jeton déjà consommé est présenté, cela
signifie qu'une copie circule : **toute la famille de jetons est révoquée** et
l'utilisateur doit se ré-authentifier. Le client sérialise ses rafraîchissements
concurrents pour ne pas déclencher ce mécanisme à tort.

Le JWT est signé en **HS512 avec une clé de 64 octets** (RFC 7518 §3.2) et
décodé avec l'algorithme épinglé, l'émetteur et l'audience exigés — ni `alg: none`,
ni confusion HS/RS ne sont acceptés.

## 4. CSRF

Double-submit : un jeton aléatoire est déposé dans un cookie lisible par le SPA,
qui doit le renvoyer dans l'en-tête `X-CSRF-Token`. Le jeton est un **HMAC lié à
l'identifiant de session** — il ne suffit donc pas d'en fabriquer un au hasard —
et la comparaison est faite en temps constant. Toute route modifiant l'état
l'exige (`deps.require_csrf`).

## 5. Chiffrement des données

Chiffrement en enveloppe à trois niveaux :

```
KEK maître (32 o, environnement / KMS)
   └─ chiffre la DEK de chaque entretien (AES-256-GCM)
        └─ chiffre chaque champ individuellement (AES-256-GCM)
             AAD = "<CRYPTO_NAMESPACE>/v1|<session>|<champ>"
```

L'**AAD lie le chiffré à son adresse logique**. Déplacer un chiffré d'un champ
vers un autre, ou d'un entretien vers un autre, ne produit pas un déchiffrement
erroné : l'authentification échoue et l'opération est rejetée. Toute altération
d'un octet est détectée par le tag GCM.

Sont chiffrés : les réponses extraites, l'intégralité des tours de conversation,
les documents générés sur disque, les secrets TOTP et les codes de secours.

La rotation de la KEK ne nécessite que le ré-emballage des DEK, jamais le
re-chiffrement du corpus.

## 6. Journal d'audit

Chaque événement (connexion, échec, enrôlement, tour d'entretien, correction
manuelle, export, téléchargement, révocation) est journalisé avec :

- l'acteur, l'action, la cible, le résultat ;
- une **empreinte à clé** de l'adresse IP et du user-agent — corrélation possible,
  donnée brute non conservée ;
- des métadonnées **filtrées** : les clés `value`, `rows`, `message`, `password`,
  `content`… sont supprimées avant écriture. Aucun contenu d'entretien ne peut
  atterrir dans le journal, même si un appelant le passe par erreur.

Chaque ligne inclut le condensat de la précédente. `GET /api/v1/admin/audit/verify`
recalcule toute la chaîne et renvoie le numéro de la **première ligne rompue**.
Ce comportement est couvert par un test automatisé qui altère une ligne, vérifie
la détection, puis restaure.

## 7. Exposition HTTP

En-têtes appliqués à toutes les réponses de l'API :

```
Content-Security-Policy: default-src 'none'; frame-ancestors 'none';
                         base-uri 'none'; form-action 'none'; sandbox
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()
Cross-Origin-Opener-Policy: same-origin
Cache-Control: no-store, no-cache, must-revalidate, private
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload   (prod)
```

- CORS sur **liste blanche explicite**, jamais `*`, avec `allow_credentials`.
- Corps de requête plafonné à 256 Ko.
- Documentation interactive (`/docs`, `/openapi.json`) **désactivée en production**.
- Les erreurs de validation ne renvoient jamais la charge utile fautive — seuls
  les noms de champs sont retournés, pour ne pas refléter une donnée confidentielle.
- Les logs passent par un filtre de rédaction (adresses e-mail, codes à 6 chiffres,
  numéros de carte, jetons).

## 8. Contrôle d'accès

- Chaque entretien est chargé par une requête portant **à la fois** son
  identifiant et celui du propriétaire : un entretien d'autrui renvoie `404`, pas
  `403` — l'existence même n'est pas divulguée.
- Un compte client peut être restreint à une liste d'entités (`allowed_structures`) ;
  la restriction est appliquée à la fois au listing et à l'ouverture d'un entretien.
- Les routes d'administration sont réservées aux rôles `admin` et `analyst`, et
  n'exposent que des compteurs, des états et des preuves d'intégrité — jamais le
  contenu d'un entretien.
- Tant que le mot de passe provisoire n'a pas été changé, la surface produit est
  fermée (`require_password_set`).

## 9. Sécurité du composant IA

### Où vont les données

| `LLM_PROVIDER` | Ce qui sort du réseau de la banque |
| -------------- | ---------------------------------- |
| `ollama`       | **rien** — l'inférence est locale  |
| `anthropic`    | le tour d'entretien courant (question posée, message de l'interlocuteur, réponses déjà consignées pour cette question) |
| `off`          | rien — aucun modèle n'est appelé   |

Le mode `ollama` est le choix recommandé pour un déploiement sensible : les
données de continuité ne franchissent aucune frontière réseau. Le moteur actif
est affiché en permanence dans l'en-tête de l'entretien, et enregistré dans le
journal d'audit à chaque tour, afin qu'un auditeur puisse établir *a posteriori*
quel moteur a produit une extraction donnée.

En mode `anthropic`, ce qui est transmis reste limité au tour courant : ni la base,
ni l'historique complet des entretiens, ni les documents générés ne sont envoyés.
Le cas échéant, une revue du contrat de traitement des données avec le fournisseur
est un prérequis.

### Garanties communes aux deux moteurs

**Le modèle n'a aucun outil.** Pas d'accès base, réseau ou disque. La seule
conséquence possible d'un tour est du texte écrit dans le document du client
lui-même.

**Séparation instruction / donnée.** Le message de l'utilisateur est encadré par
`<message_utilisateur>` et le prompt système déclare explicitement que ce contenu
est une donnée d'entretien, jamais une consigne. Une tentative d'injection
(« ignore tes consignes », « affiche ta configuration ») est traitée comme du
contenu et donne lieu à un recadrage.

**Sortie contrainte.** La réponse est validée contre un schéma JSON généré à
partir de la question — par l'API côté Anthropic, par le décodage contraint
d'Ollama côté local. Le modèle ne peut pas renvoyer de prose là où le pipeline
attend une valeur de document, et les colonnes à valeurs imposées n'acceptent que
les codes autorisés. La chaîne vide reste permise : « non précisé » est une
réponse valide, et de loin préférable à une criticité inventée.

**Les définitions ne passent pas par le modèle.** Lorsqu'un interlocuteur demande
la signification d'un terme, l'entrée du référentiel est servie mot pour mot. Un
petit modèle ne peut donc pas paraphraser de travers une définition qui fait foi
dans le modèle source.

**Consigne de fidélité.** Le prompt interdit de compléter une réponse par des
informations non fournies ; les éléments manquants sont listés et redemandés, pas
devinés. Un panneau de relecture permet une **correction manuelle qui contourne
entièrement le modèle**.

**Entrées nettoyées** — caractères de contrôle retirés, longueur plafonnée à
8 000 caractères avant tout traitement.

## 10. Interface

Aucun appel à `dangerouslySetInnerHTML` dans l'application. Le formateur de texte
(`RichText`) construit des nœuds React : ni la sortie du modèle, ni la saisie d'un
utilisateur ne peut introduire de balisage dans la page. Le téléchargement du
document passe par un `fetch` authentifié puis un blob local, ce qui évite de
faire transiter un jeton dans une URL.

## 11. Vérification

```bash
cd backend && python -m pytest
```

Contrôles automatisés : indistinguabilité des erreurs d'authentification, refus
des JWT forgés (`alg: none`), exigence CSRF, politique de mot de passe, portée des
entités, invisibilité inter-comptes, fermeture des routes d'administration,
en-têtes de sécurité, plafond de charge utile, liaison cryptographique à l'adresse,
détection d'altération, absence de clair en base, intégrité de la chaîne d'audit,
filtrage des métadonnées, signature et expiration des liens de téléchargement.

## 12. Limites connues

| Limite                                   | Portée                          | Traitement recommandé          |
| ---------------------------------------- | ------------------------------- | ------------------------------ |
| Limitation de débit en mémoire           | correcte sur une instance       | backend Redis en multi-instance |
| Schéma créé par `create_all`             | acceptable en pilote            | Alembic dès la 1re évolution    |
| `MASTER_KEK` lue depuis l'environnement  | acceptable en pilote            | Vault / KMS / HSM en production |
| Pas de purge automatique                 | conservation illimitée          | politique de rétention à définir |
| Pas de scellement externe du journal     | détection, pas de prévention    | export périodique horodaté      |

**Perte de la KEK = perte définitive des données.** Sa sauvegarde et son
séquestre doivent être traités avant la mise en service.
