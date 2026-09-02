"""Create ready-to-use test logins, for trying the application out.

    python -m app.scripts.demo_account

Two accounts, both with a known password and a **known TOTP secret**, so you can
sign in without a phone: the script prints the current six-digit code, and the
`otpauth://` URI if you would rather add it to an authenticator.

    test@exemple.fr         client   sees every structure
    test.admin@exemple.fr   admin    the oversight screen and reset

Re-running refreshes both: password reset, second factor reinstated, lockout
lifted, forced password change cleared. So a login that has drifted - changed
password, enrolled phone, too many failed attempts - is always one command from
working again.

WHY THE SECRET IS FIXED, AND WHY THIS REFUSES TO RUN IN PRODUCTION

The application requires a second factor, and rightly so. Bypassing it for a
test account would mean weakening REQUIRE_TOTP for everyone, so instead the
factor stays mandatory and its secret is simply known in advance. That is
perfectly fine on a laptop and completely unacceptable on a server, which is why
this script stops when ENV=prod. Convenience that cannot be deployed by accident.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Tuple

import pyotp
from sqlalchemy import select

from app.core import audit, security
from app.core.config import settings
from app.core.crypto import vault_seal
from app.db.models import User
from app.db.session import SessionLocal, init_db

# Fixed on purpose - see the module docstring. Valid base32, 32 characters.
DEMO_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
DEMO_PASSWORD = "Test-PCA-2026!demo"

# (email, full name, role, organisation, allowed structures)
DEMO_ACCOUNTS: List[Tuple[str, str, str, str, Optional[str]]] = [
    # Unrestricted, unlike the real per-entity logins: a tester needs to reach
    # any structure to exercise the picker and both question plans.
    ("test@exemple.fr", "Compte de test", "client", "Test", None),
    ("test.admin@exemple.fr", "Administrateur de test", "admin", "Test", None),
]


def _apply(db, email: str, full_name: str, role: str, org: str, allowed, password: str):
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    created = user is None
    if user is None:
        user = User(email=email)
        db.add(user)

    user.full_name = full_name
    user.organisation = org
    user.role = role
    user.allowed_structures = allowed
    user.password_hash = security.hash_password(password)
    user.must_change_password = False
    user.is_active = True
    user.failed_logins = 0
    user.locked_until = None
    db.flush()

    # Sealed the same way a real enrolment seals it - the account is ordinary in
    # every respect except that we chose its secret.
    user.totp_secret_enc = vault_seal(DEMO_TOTP_SECRET, f"totp:{user.id}")
    user.totp_enabled = True
    return created


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Comptes de test prêts à l'emploi")
    parser.add_argument(
        "--password", default=DEMO_PASSWORD, help=f"mot de passe (défaut : {DEMO_PASSWORD})"
    )
    args = parser.parse_args(argv)

    if settings.is_prod:
        print(
            "  Refusé : ENV=prod.\n"
            "  Ces comptes ont un mot de passe et un secret TOTP connus d'avance ;\n"
            "  ils n'ont rien à faire sur un serveur. Utilisez app.scripts.seed.",
            file=sys.stderr,
        )
        return 2

    problems = security.password_problems(args.password)
    if problems:
        print(f"  Mot de passe refusé : {problems}", file=sys.stderr)
        return 2

    init_db()
    with SessionLocal() as db:
        results = [
            (email, role, _apply(db, email, name, role, org, allowed, args.password))
            for email, name, role, org, allowed in DEMO_ACCOUNTS
        ]
        audit.record(
            db, action="admin.demo_accounts", target="", meta={"count": len(results)}
        )
        db.commit()

    now = pyotp.TOTP(DEMO_TOTP_SECRET)
    width = max(len(e) for e, _, _ in results)

    print()
    print("  Comptes de test prêts :")
    print()
    for email, role, created in results:
        print(f"    {email.ljust(width)}   {role:6}   {'créé' if created else 'réinitialisé'}")
    print()
    print(f"    Mot de passe   : {args.password}")
    print(f"    Code à 6 chiffres (valable ~30 s) : {now.now()}")
    print()
    print(f"    Secret TOTP    : {DEMO_TOTP_SECRET}")
    print(f"    otpauth        : {now.provisioning_uri(name=DEMO_ACCOUNTS[0][0], issuer_name='Etat des lieux (test)')}")
    print()
    print("  Le code change toutes les 30 s : relancez ce script pour en obtenir")
    print("  un nouveau, ou ajoutez le secret à votre application d'authentification.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
