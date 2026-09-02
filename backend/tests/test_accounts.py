"""One login per entity, each confined to its own structure.

A single shared participant login meant one correspondent at a time, and no way
to tell from the record who answered for which entity. These tests pin the
replacement: an address per structure, scoped by `allowed_structures`.
"""
from __future__ import annotations

import csv
import os

import pytest
import subprocess
import sys
from pathlib import Path

from app.core.config import settings
from app.scripts import seed
from tests.conftest import API, ROOT, authenticate


# --------------------------------------------------------------------------- #
# The account list
# --------------------------------------------------------------------------- #
def test_every_structure_gets_its_own_login():
    accounts = seed.participant_accounts()
    assert len(accounts) == len(seed.STRUCTURES)

    codes = {a[4] for a in accounts}
    assert codes == {s[0] for s in seed.STRUCTURES}, "one account per structure"
    assert len({a[0] for a in accounts}) == len(accounts), "addresses are unique"


def test_an_entity_login_is_scoped_to_exactly_one_structure():
    """A single code in `allowed_structures` is what confines the catalogue."""
    for email, _name, role, _org, allowed in seed.participant_accounts():
        assert role == "client"
        assert allowed and "," not in allowed, f"{email} must see a single structure"


def test_addresses_follow_the_configured_domain():
    """Derived from the code, not a person: the correspondent may change."""
    domain = settings.PARTICIPANT_EMAIL_DOMAIN
    for email, _n, _r, _o, code in seed.participant_accounts():
        assert email == f"{code.lower()}@{domain}"


def test_the_shared_login_is_retired_not_merely_dropped():
    """It stays in the database so audit entries still point at a real user."""
    assert "participant@mansabank.tn" in seed.RETIRED
    assert all(a[0] not in seed.RETIRED for a in seed.ACCOUNTS)
    assert all(a[0] not in seed.RETIRED for a in seed.participant_accounts())


# --------------------------------------------------------------------------- #
# What a scoped login can actually reach
# --------------------------------------------------------------------------- #
def test_a_scoped_account_sees_only_its_own_structure(client):
    """The fixture interviewee is scoped to DSI, exactly as the real ones are."""
    headers = authenticate(client, "client@example.com")
    catalogue = client.get(f"{API}/structures", headers=headers).json()

    assert len(catalogue) == 1, "a scoped login must not see the whole org chart"
    assert catalogue[0]["code"] == "DSI"


def test_a_scoped_account_cannot_open_another_entity(client):
    admin = authenticate(client, "staff@example.org")
    every = client.get(f"{API}/structures", headers=admin).json()
    assert len(every) > 1, "staff see the whole catalogue"
    forbidden = next(s for s in every if s["code"] != "DSI")

    headers = authenticate(client, "client@example.com")
    refused = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": forbidden["id"]}
    )
    assert refused.status_code == 403, "scoping is enforced server-side, not just hidden"


# --------------------------------------------------------------------------- #
# Distributing the credentials
# --------------------------------------------------------------------------- #
def test_the_credentials_file_lists_every_entity(tmp_path):
    """32 passwords cannot be copied out of a console.

    Run in a subprocess against its own database: the seed creates the real
    catalogue, which must not leak into the suite's fixture data.
    """
    target = tmp_path / "identifiants.csv"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+pysqlite:///{(tmp_path / 'seed.db').as_posix()}",
        "PARTICIPANT_EMAIL_DOMAIN": "entites.example.com",
        "PYTHONIOENCODING": "utf-8",
    }
    done = subprocess.run(
        [sys.executable, "-m", "app.scripts.seed", "--credentials-file", str(target)],
        cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8",
    )
    assert done.returncode == 0, done.stderr

    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))

    codes = {r["Code"] for r in rows if r["Code"]}
    assert codes == {s[0] for s in seed.STRUCTURES}, "every entity is in the file"
    assert all(r["Mot de passe provisoire"] for r in rows)
    assert all(r["Entite"] for r in rows), "staff rows say Administration, not a dash"

    entity = next(r for r in rows if r["Code"] == "ACF")
    assert entity["Adresse"] == "acf@entites.example.com"


def test_seeding_twice_creates_nothing_new(tmp_path):
    """Re-running on an update must not mint a second set of passwords."""
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+pysqlite:///{(tmp_path / 'seed.db').as_posix()}",
        "PYTHONIOENCODING": "utf-8",
    }
    run = lambda: subprocess.run(  # noqa: E731
        [sys.executable, "-m", "app.scripts.seed"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8",
    )
    first = run()
    assert first.returncode == 0, first.stderr
    assert "compte(s) créé(s)" in first.stdout

    second = run()
    assert second.returncode == 0, second.stderr
    assert "Aucun nouveau compte" in second.stdout


# --------------------------------------------------------------------------- #
# The domain has to be one the login endpoint will accept
# --------------------------------------------------------------------------- #
def test_the_default_domain_produces_addresses_that_can_sign_in():
    """A reserved suffix builds 32 accounts that exist and can never log in.

    Nothing stops the database storing `acf@entites.local`; the address
    validator on /auth/login rejects it, and only when someone tries. Re-seeding
    does not rename an account, so the mistake is expensive to undo.
    """
    from pydantic import BaseModel, EmailStr

    class _Probe(BaseModel):
        email: EmailStr

    for email, _n, _r, _o, _c in seed.participant_accounts():
        _Probe(email=email)          # raises if the endpoint would refuse it


@pytest.mark.parametrize("domain", ["entites.local", "x.test", "y.invalid", "z.localhost"])
def test_a_reserved_domain_is_refused_before_anything_is_written(domain, monkeypatch):
    monkeypatch.setattr(settings, "PARTICIPANT_EMAIL_DOMAIN", domain)
    with pytest.raises(SystemExit) as refused:
        seed.participant_accounts()
    assert "PARTICIPANT_EMAIL_DOMAIN" in str(refused.value)


def test_the_demo_accounts_can_also_sign_in():
    from pydantic import BaseModel, EmailStr

    from app.scripts import demo_account

    class _Probe(BaseModel):
        email: EmailStr

    for email, _n, _r, _o, _a in demo_account.DEMO_ACCOUNTS:
        _Probe(email=email)


def test_the_demo_script_refuses_to_run_in_production(monkeypatch):
    """Known password, known second factor - it must never reach a server."""
    from app.scripts import demo_account

    monkeypatch.setattr(settings, "ENV", "prod")
    assert demo_account.main([]) == 2
