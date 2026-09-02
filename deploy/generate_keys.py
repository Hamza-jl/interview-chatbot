"""Génère les quatre secrets du déploiement, prêts à coller dans .env.

    python deploy/generate_keys.py

Rien n'est écrit sur le disque : les valeurs sont affichées une fois. Copiez-les
dans le .env, et conservez MASTER_KEK ailleurs qu'sur la machine - le perdre
rend illisibles, définitivement, toutes les réponses déjà chiffrées.

Aucune dépendance : `secrets` et `base64` sont dans la bibliothèque standard,
donc ce script tourne sur le portable-serveur avant toute installation.
"""
from __future__ import annotations

import base64
import secrets
import string
import sys


def key(nbytes: int) -> str:
    """Clé aléatoire encodée en base64, comme les settings l'attendent."""
    return base64.b64encode(secrets.token_bytes(nbytes)).decode()


def password(length: int = 28) -> str:
    """Mot de passe Postgres : pas de caractère qui gêne dans une URL."""
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> int:
    print()
    print("  Collez ces quatre lignes dans le fichier .env :")
    print()
    print(f"MASTER_KEK={key(32)}")
    print(f"JWT_SECRET={key(64)}")
    print(f"DOWNLOAD_SIGNING_KEY={key(32)}")
    print(f"POSTGRES_PASSWORD={password()}")
    print()
    print("  MASTER_KEK déchiffre toutes les réponses. Sauvegardez-la hors de")
    print("  cette machine, et ne la régénérez jamais sur un déploiement en")
    print("  service : les données existantes deviendraient illisibles.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
