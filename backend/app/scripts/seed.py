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
    # The organisation chart of the entity being documented. Only `code` and
    # `template_kind` matter to the engine: "dsi" selects the longer IT
    # questionnaire, "entite" the business-unit one.
    ("SI",  "Systèmes d'Information", "Transformation & Digital", "dsi"),

    # --- Banque de financement --------------------------------------------
    ("ENT", "Entreprises & Institutionnels", "Banque de Financement", "entite"),
    ("PME", "PME & Professionnels", "Banque de Financement", "entite"),
    ("CAG", "Commodities & Agribusiness", "Banque de Financement", "entite"),
    ("CPA", "Clientèle Patrimoniale", "Banque de Financement", "entite"),
    ("SDM", "Salle de Marchés", "Banque de Financement", "entite"),
    ("TRD", "Trade", "Banque de Financement", "entite"),
    ("FST", "Financements Structurés", "Banque de Financement", "entite"),
    ("ACE", "Analyse de Crédit Entreprise", "Banque de Financement", "entite"),

    # --- Transformation & Digital ------------------------------------------
    ("PSD", "Produits et Solutions Digitales", "Transformation & Digital", "entite"),
    ("PAD", "Partenariats & Distribution", "Transformation & Digital", "entite"),
    ("CMG", "Cash Management", "Transformation & Digital", "entite"),
    ("TDA", "Transformation Digitale & Data Analytics", "Transformation & Digital", "entite"),

    # --- Risques, conformité et audit --------------------------------------
    ("RIS", "Gestion des Risques", "Risques & Contrôle", "entite"),
    ("CFT", "Conformité", "Risques & Contrôle", "entite"),
    ("SSI", "Sécurité Système d'Information", "Risques & Contrôle", "entite"),
    ("ATE", "Audit Technologique", "Risques & Contrôle", "entite"),
    ("ACF", "Audit Comptable et Financier", "Risques & Contrôle", "entite"),

    # --- Opérations et fonctions support -----------------------------------
    ("OPE", "Opérations", "Opérations & Support", "entite"),
    ("EXC", "Expérience Client", "Opérations & Support", "entite"),
    ("QUA", "Qualité", "Opérations & Support", "entite"),
    ("CQP", "Crédits et Qualité de Portefeuille", "Opérations & Support", "entite"),
    ("ADC", "Administration du Crédit", "Opérations & Support", "entite"),
    ("AJU", "Affaires Juridiques", "Opérations & Support", "entite"),
    ("CPR", "Comptabilité & Reporting", "Opérations & Support", "entite"),
    ("CCO", "Contrôle Comptabilité", "Opérations & Support", "entite"),
    ("CDG", "Contrôle de Gestion", "Opérations & Support", "entite"),
    ("SGE", "Services Généraux", "Opérations & Support", "entite"),
    ("MKC", "Marketing & Communication", "Opérations & Support", "entite"),
    ("GPR", "Gestion Projets", "Opérations & Support", "entite"),

    # --- Capital humain -----------------------------------------------------
    ("GCH", "Gestion administrative Capital Humain", "Capital Humain", "entite"),
    ("DCH", "Développement Capital Humain", "Capital Humain", "entite"),
]

# (email, full name, role, organisation, allowed structure codes or None)
ACCOUNTS = [
    # Two logins only. The interviewee account is shared and unrestricted:
    # `allowed_structures=None` lets it open any entity, so the person picks
    # their own from the catalogue after signing in.
    ("participant@mansabank.tn", "Participant", "client", "MANSA Bank", None),
    ("admin@devoteam.com", "Administrateur plateforme", "admin", "Devoteam", None),
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

    print("\n  Catalogue des structures : à jour.\n")
    if created:
        print("  Comptes créés - notez ces mots de passe, ils ne seront plus affiches :\n")
        width = max(len(e) for e, _ in created)
        for email, password in created:
            print(f"    {email.ljust(width)}   {password}")
        print(
            "\n  A la première connexion, chaque compte doit :\n"
            "    1. enroler une application d'authentification (TOTP),\n"
            "    2. définir un nouveau mot de passe.\n"
        )
    else:
        print("  Aucun nouveau compte : la base contenait déjà ces utilisateurs.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
