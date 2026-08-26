"""Reset a user's credentials - lost phone, forgotten password, handover.

    python -m app.scripts.reset_account prenom.nom@example.com
    python -m app.scripts.reset_account --all --clients

Issues a fresh provisional password (printed once), clears the second factor so
the account re-enrols on next login, lifts any lockout, and revokes every live
browser session. Every action is written to the audit chain.
"""
from __future__ import annotations

import argparse
import secrets
import string
import sys
from typing import List

from sqlalchemy import select

from app.core import audit, security
from app.db.models import AuthSession, User, utcnow
from app.db.session import SessionLocal, init_db

_ALPHABET = string.ascii_letters + string.digits + "!@#$%&*?-_"


def strong_password(length: int = 18) -> str:
    while True:
        candidate = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not security.password_problems(candidate):
            return candidate


def reset(db, user: User) -> str:
    password = strong_password()
    user.password_hash = security.hash_password(password)
    user.must_change_password = True

    # Clearing the seed forces a fresh enrolment - the old authenticator entry
    # and the old recovery codes stop working immediately.
    user.totp_enabled = False
    user.totp_secret_enc = None
    user.recovery_codes_enc = None

    user.failed_attempts = 0
    user.locked_until = None

    for session in db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
        )
    ).scalars():
        session.revoked_at = utcnow()
        session.revoked_reason = "credential_reset"

    audit.record(db, action="admin.credential_reset", actor_id=user.id, target=user.email)
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset credentials for one or more accounts")
    parser.add_argument("emails", nargs="*", help="accounts to reset")
    parser.add_argument("--all", action="store_true", help="reset every account")
    parser.add_argument("--clients", action="store_true", help="restrict --all to client accounts")
    args = parser.parse_args()

    if not args.emails and not args.all:
        parser.error("give at least one email address, or --all")

    init_db()
    issued: List[tuple[str, str]] = []

    with SessionLocal() as db:
        if args.all:
            stmt = select(User)
            if args.clients:
                stmt = stmt.where(User.role == "client")
            targets = list(db.execute(stmt.order_by(User.email)).scalars())
        else:
            targets = []
            for email in args.emails:
                user = db.execute(
                    select(User).where(User.email == email.lower().strip())
                ).scalar_one_or_none()
                if user is None:
                    print(f"  compte introuvable : {email}", file=sys.stderr)
                    continue
                targets.append(user)

        for user in targets:
            issued.append((user.email, reset(db, user)))
        db.commit()

    if not issued:
        print("\n  Aucun compte reinitialise.\n")
        return 1

    width = max(len(email) for email, _ in issued)
    print("\n  Mots de passe provisoires - transmis par canal sur, affiches une seule fois :\n")
    for email, password in issued:
        print(f"    {email.ljust(width)}   {password}")
    print(
        "\n  A la prochaine connexion, chaque compte devra :\n"
        "    1. enroler a nouveau une application d'authentification (TOTP),\n"
        "    2. definir un nouveau mot de passe.\n"
        "  Les sessions ouvertes ont ete revoquees.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
