"""Create an example structure catalogue and the initial accounts.

    python -m app.scripts.seed

Passwords are generated, printed once, and flagged ``must_change_password``.
Re-running the script is safe: existing rows are left untouched.
"""
from __future__ import annotations

import secrets
import string
from typing import List, Tuple

from sqlalchemy import select

from app.core import security
from app.db.models import Structure, User
from app.db.session import SessionLocal, init_db

# (code, name, parent, template_kind)
STRUCTURES: List[Tuple[str, str, str, str]] = [
    # Sample catalogue. Replace with the real one for a deployment; only `code`
    # and `template_kind` matter to the engine.
    ("DSI", "Direction des Systemes d'Information", "Direction Generale", "dsi"),
    ("DEX", "Direction de l'Exploitation", "Direction Generale", "entite"),
    ("DCR", "Direction du Credit", "Direction Generale Adjointe", "entite"),
    ("DRI", "Direction des Risques", "Direction Generale", "entite"),
    ("DFC", "Direction Financiere et Comptable", "Direction Generale Adjointe", "entite"),
    ("DRH", "Direction des Ressources Humaines", "Direction Generale", "entite"),
    ("DJU", "Direction Juridique", "Direction Generale Adjointe", "entite"),
    ("DCO", "Direction de la Conformite", "Direction Generale", "entite"),
    ("DOR", "Direction Organisation et Qualite", "Direction Generale", "entite"),
]

# (email, full name, role, organisation, allowed structure codes or None)
ACCOUNTS = [
    # Example accounts on RFC 2606 reserved domains - replace before any real use.
    ("dsi@example.com", "Responsable SI", "client", "Organisation", "DSI"),
    ("credit@example.com", "Responsable Credit", "client", "Organisation", "DCR"),
    ("pilote@example.com", "Pilote PCA", "client", "Organisation", None),
    ("consultant@example.org", "Consultant PCA", "analyst", "Cabinet conseil", None),
    ("admin@example.org", "Administrateur plateforme", "admin", "Cabinet conseil", None),
]

_ALPHABET = string.ascii_letters + string.digits + "!@#$%&*?-_"


def strong_password(length: int = 18) -> str:
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not security.password_problems(candidate):
            return candidate


def main() -> int:
    init_db()
    created: List[Tuple[str, str]] = []

    with SessionLocal() as db:
        for code, name, parent, kind in STRUCTURES:
            if db.execute(select(Structure).where(Structure.code == code)).scalar_one_or_none():
                continue
            db.add(Structure(code=code, name=name, parent=parent, template_kind=kind))

        for email, full_name, role, org, allowed in ACCOUNTS:
            if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
                continue
            password = strong_password()
            db.add(
                User(
                    email=email,
                    full_name=full_name,
                    organisation=org,
                    role=role,
                    password_hash=security.hash_password(password),
                    must_change_password=True,
                    allowed_structures=allowed,
                )
            )
            created.append((email, password))

        db.commit()

    print("\n  Catalogue des structures : a jour.\n")
    if created:
        print("  Comptes crees - notez ces mots de passe, ils ne seront plus affiches :\n")
        width = max(len(e) for e, _ in created)
        for email, password in created:
            print(f"    {email.ljust(width)}   {password}")
        print(
            "\n  A la premiere connexion, chaque compte doit :\n"
            "    1. enroler une application d'authentification (TOTP),\n"
            "    2. definir un nouveau mot de passe.\n"
        )
    else:
        print("  Aucun nouveau compte : la base contenait deja ces utilisateurs.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
