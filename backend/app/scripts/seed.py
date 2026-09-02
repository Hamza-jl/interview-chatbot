"""Create an example structure catalogue and the initial accounts.

    python -m app.scripts.seed

Passwords are generated, printed once, and flagged ``must_change_password``.
Re-running the script is safe: existing rows are left untouched.
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import secrets
import string
from typing import List, Optional, Tuple

from sqlalchemy import select

from app.core import security
from app.core.config import settings
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
    ("admin@devoteam.com", "Administrateur plateforme", "admin", "Devoteam", None),

    # L'équipe qui suit la collecte. Rôle « admin » : consultation de
    # l'avancement de toutes les entités et réinitialisation d'un entretien.
    # Aucun de ces comptes ne peut lire le contenu des réponses.
    ("zouheir.belkahia@devoteam.com", "Zouheir Belkahia", "admin", "Devoteam", None),
    ("tarek.akrout@devoteam.com", "Tarek Akrout", "admin", "Devoteam", None),
    ("mohamed.amir.essghir@devoteam.com", "Mohamed Amir Essghir", "admin", "Devoteam", None),
    ("faten.taghouti@devoteam.com", "Faten Taghouti", "admin", "Devoteam", None),
    ("mohamed.ben.ayed@devoteam.com", "Mohamed Ben Ayed", "admin", "Devoteam", None),

    # Comptes de recette, créés partout, y compris sur le serveur. Le client
    # n'est bridé sur aucune structure : il faut pouvoir dérouler les deux plans
    # de questions et le choix d'entité. Leurs mots de passe sont générés et
    # affichés comme les autres - rien n'est connu d'avance.
    ("test@devoteam.com", "Compte de test", "client", "Devoteam", None),
    ("test.admin@devoteam.com", "Administrateur de test", "admin", "Devoteam", None),
]

# Logins replaced by the per-entity accounts below. Left in the database so no
# audit entry points at a vanished user, but deactivated: a single shared login
# meant one correspondent at a time, and no way to tell who answered what.
RETIRED = ["participant@mansabank.tn"]


def _check_domain(domain: str) -> None:
    """Refuse a domain the login endpoint would later reject.

    Nothing stops the database storing `acf@entites.local`; the address
    validator on /auth/login does, and only when someone tries to sign in. The
    32 accounts would already exist by then, and re-seeding does not rename
    them. Better to fail here, before anything is written.
    """
    from pydantic import BaseModel, EmailStr, ValidationError

    class _Probe(BaseModel):
        email: EmailStr

    try:
        _Probe(email=f"probe@{domain}")
    except ValidationError as exc:  # noqa: BLE001
        raise SystemExit(
            f"\n  PARTICIPANT_EMAIL_DOMAIN={domain!r} ne peut pas servir d'adresse.\n"
            "  Les suffixes réservés (.local, .test, .invalid, .localhost) sont\n"
            "  refusés à la connexion : les comptes seraient créés sans pouvoir\n"
            "  jamais se connecter. Utilisez un domaine ordinaire.\n"
        ) from exc


def participant_accounts() -> List[Tuple[str, str, str, str, str]]:
    """One login per entity, each locked to its own structure.

    `allowed_structures` holds a single code, so the catalogue this account sees
    has exactly one entry and the picker selects it automatically. The address
    is derived from the code rather than a person's name: these accounts belong
    to entities, and a correspondent may change.
    """
    domain = settings.PARTICIPANT_EMAIL_DOMAIN
    _check_domain(domain)
    return [
        (f"{code.lower()}@{domain}", name, "client", settings.CLIENT_NAME, code)
        for code, name, _parent, _kind in STRUCTURES
    ]


_ALPHABET = string.ascii_letters + string.digits + "!@#$%&*?-_"


def strong_password(length: int = 18) -> str:
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not security.password_problems(candidate):
            return candidate


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials-file",
        metavar="CHEMIN",
        help="écrit les identifiants créés dans un CSV (mots de passe EN CLAIR)",
    )
    args = parser.parse_args(argv)

    init_db()
    created: List[Tuple[str, str, str]] = []
    retired = 0

    with SessionLocal() as db:
        for code, name, parent, kind in STRUCTURES:
            if db.execute(select(Structure).where(Structure.code == code)).scalar_one_or_none():
                continue
            db.add(Structure(code=code, name=name, parent=parent, template_kind=kind))

        # Structures must exist before the accounts that point at them.
        db.flush()

        for email in RETIRED:
            legacy = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if legacy is not None and legacy.is_active:
                legacy.is_active = False
                retired += 1

        for email, full_name, role, org, allowed in ACCOUNTS + participant_accounts():
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
            created.append((email, password, allowed or "—"))

        db.commit()

    print("\n  Catalogue des structures : à jour.")
    if retired:
        print(f"  {retired} compte(s) partagé(s) désactivé(s).")
    print()

    if not created:
        print("  Aucun nouveau compte : la base contenait déjà ces utilisateurs.\n")
        return 0

    width = max(len(e) for e, _, _ in created)
    print(f"  {len(created)} compte(s) créé(s). Ces mots de passe ne seront plus affichés :\n")
    for email, password, scope in created:
        print(f"    {email.ljust(width)}   {password}   {scope}")
    print(
        "\n  À la première connexion, chaque compte doit :\n"
        "    1. enrôler une application d'authentification (TOTP),\n"
        "    2. définir un nouveau mot de passe.\n"
    )

    if args.credentials_file:
        # 32 mots de passe ne se recopient pas depuis une console. Le fichier
        # est un pis-aller assumé : il porte des secrets en clair, il sert à
        # les distribuer, et il se supprime une fois la distribution faite.
        target = pathlib.Path(args.credentials_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Entite", "Code", "Adresse", "Mot de passe provisoire"])
            names = {c: n for c, n, _p, _k in STRUCTURES}
            for email, password, scope in created:
                # A staff login is scoped to nothing in particular; saying so
                # beats a dash in a file someone has to read and act on.
                entity = names.get(scope, "Administration")
                writer.writerow([entity, scope if scope in names else "", email, password])
        print(f"  Identifiants écrits dans : {target}")
        print("  Fichier en clair : distribuez, puis supprimez-le.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
