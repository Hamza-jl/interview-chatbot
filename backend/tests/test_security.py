"""Security controls: authentication, isolation, CSRF, crypto, audit integrity."""
from __future__ import annotations

import base64

import pytest
from sqlalchemy import select

from tests.conftest import API, PASSWORD, authenticate


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def test_unknown_account_and_wrong_password_are_indistinguishable(client):
    wrong = client.post(
        f"{API}/auth/login", json={"email": "client@example.com", "password": "not-the-password"}
    )
    unknown = client.post(
        f"{API}/auth/login", json={"email": "ghost@nowhere.tn", "password": "not-the-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_totp_is_required_before_a_session_is_issued(client):
    res = client.post(
        f"{API}/auth/login", json={"email": "client@example.com", "password": PASSWORD}
    )
    body = res.json()
    assert body["stage"] in {"totp_required", "totp_enrollment"}
    assert body["session"] is None
    assert body["challenge"]


def test_protected_route_rejects_missing_and_forged_tokens(client):
    assert client.get(f"{API}/structures").status_code == 401
    assert client.get(f"{API}/structures", headers={"Authorization": "Bearer nonsense"}).status_code == 401

    # A token signed with the "none" algorithm must not be accepted.
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(b'{"sub":"x","role":"admin","sid":"x"}').decode().rstrip("=")
    forged = f"{header}.{payload}."
    assert client.get(f"{API}/structures", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_csrf_token_is_required_for_state_changing_calls(client):
    headers = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=headers).json()

    without = {"Authorization": headers["Authorization"]}
    denied = client.post(f"{API}/sessions", headers=without, json={"structure_id": structures[0]["id"]})
    assert denied.status_code == 403

    wrong = {**without, "X-CSRF-Token": "forged.value"}
    assert client.post(f"{API}/sessions", headers=wrong, json={"structure_id": structures[0]["id"]}).status_code == 403


def test_password_policy_rejects_predictable_secrets(client):
    from app.core.security import password_problems

    assert password_problems("Devoteam2026!x")          # contains a banned term
    assert password_problems("short1!A")                 # too short
    assert password_problems("nouppercase123!")          # no uppercase
    assert password_problems("nadia@bank.tn", "nadia@bank.tn")  # contains the identifier
    assert password_problems("Zephyr!Kadence7#Vlt") == []


# --------------------------------------------------------------------------- #
# Authorisation and tenant isolation
# --------------------------------------------------------------------------- #
def test_client_only_sees_structures_it_is_entitled_to(client):
    headers = authenticate(client, "client@example.com")
    codes = {s["code"] for s in client.get(f"{API}/structures", headers=headers).json()}
    assert codes == {"DSI"}, "the account is scoped to DSI only"


def test_client_cannot_open_a_structure_outside_its_scope(client):
    staff = authenticate(client, "staff@example.org")
    all_structures = client.get(f"{API}/structures", headers=staff).json()
    forbidden = next(s for s in all_structures if s["code"] == "DCR")

    headers = authenticate(client, "client@example.com")
    res = client.post(f"{API}/sessions", headers=headers, json={"structure_id": forbidden["id"]})
    assert res.status_code == 403


def test_a_session_is_invisible_to_another_account(client):
    owner = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=owner).json()
    session_id = client.post(
        f"{API}/sessions", headers=owner, json={"structure_id": structures[0]["id"]}
    ).json()["state"]["id"]

    intruder = authenticate(client, "staff@example.org")
    assert client.get(f"{API}/sessions/{session_id}", headers=intruder).status_code == 404


def test_admin_surface_is_closed_to_clients(client):
    headers = authenticate(client, "client@example.com")
    assert client.get(f"{API}/admin/audit/verify", headers=headers).status_code == 403
    assert client.get(f"{API}/admin/overview", headers=headers).status_code == 403


# --------------------------------------------------------------------------- #
# Transport hardening
# --------------------------------------------------------------------------- #
def test_security_headers_are_present_on_every_response(client):
    headers = client.get("/health").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "no-store" in headers["Cache-Control"]


def test_oversized_payloads_are_refused(client):
    headers = authenticate(client, "client@example.com")
    res = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": "x" * 400_000}
    )
    assert res.status_code in {413, 422}


# --------------------------------------------------------------------------- #
# Cryptography
# --------------------------------------------------------------------------- #
def test_field_ciphertext_is_bound_to_its_address(client):
    from app.core.crypto import DecryptionError, new_dek, open_sealed, seal

    dek = new_dek()
    blob = seal(dek, "session-A", "answer:q1", "Effectif : 42 collaborateurs")

    assert open_sealed(dek, "session-A", "answer:q1", blob) == "Effectif : 42 collaborateurs"

    # The same ciphertext must not decrypt at a different address.
    with pytest.raises(DecryptionError):
        open_sealed(dek, "session-A", "answer:q2", blob)
    with pytest.raises(DecryptionError):
        open_sealed(dek, "session-B", "answer:q1", blob)
    with pytest.raises(DecryptionError):
        open_sealed(new_dek(), "session-A", "answer:q1", blob)


def test_tampering_with_a_ciphertext_is_detected(client):
    from app.core.crypto import DecryptionError, new_dek, open_sealed, seal

    dek = new_dek()
    blob = seal(dek, "s", "f", "valeur confidentielle")
    raw = bytearray(base64.b64decode(blob))
    raw[-1] ^= 0x01
    with pytest.raises(DecryptionError):
        open_sealed(dek, "s", "f", base64.b64encode(bytes(raw)).decode())


def test_answers_are_never_stored_in_clear(client):
    from app.db.models import Answer, ChatMessage
    from app.db.session import SessionLocal

    headers = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=headers).json()
    session_id = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": structures[0]["id"]}
    ).json()["state"]["id"]

    secret = "Le RSSI est M. Karim Trabelsi, poste 4417"
    client.post(f"{API}/sessions/{session_id}/messages", headers=headers, json={"message": secret})

    with SessionLocal() as db:
        stored = " ".join(
            row.payload_enc for row in db.execute(select(Answer)).scalars()
        ) + " ".join(row.body_enc for row in db.execute(select(ChatMessage)).scalars())

    assert "Trabelsi" not in stored
    assert "4417" not in stored


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #
def test_audit_chain_verifies_and_detects_tampering(client):
    from app.core.audit import verify_chain
    from app.db.models import AuditLog
    from app.db.session import SessionLocal

    staff = authenticate(client, "staff@example.org")
    assert client.get(f"{API}/admin/audit/verify", headers=staff).json()["valid"] is True

    with SessionLocal() as db:
        row = db.execute(select(AuditLog).order_by(AuditLog.seq).limit(1)).scalar_one()
        original, row.action = row.action, "quietly.rewritten"
        db.commit()

        report = verify_chain(db)
        assert report["valid"] is False
        assert report["broken_at"] == row.seq

        row.action = original
        db.commit()
        assert verify_chain(db)["valid"] is True


def test_audit_entries_never_carry_interview_content(client):
    from app.core.audit import record
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        entry = record(
            db, action="survey.turn", actor_id="u1",
            meta={"question_id": "dsi.risques.it", "value": "secret bancaire", "rows": [1, 2]},
        )
        db.commit()
        assert "secret bancaire" not in entry.meta
        assert "dsi.risques.it" in entry.meta


# --------------------------------------------------------------------------- #
# Signed downloads
# --------------------------------------------------------------------------- #
def test_download_tokens_are_signed_scoped_and_expiring(client):
    import time

    from app.core.security import sign_download, verify_download

    token = sign_download("export-1", "user-1")
    assert verify_download(token) == ("export-1", "user-1")

    assert verify_download(token[:-2] + "00") is None       # bad signature
    assert verify_download("garbage") is None

    expired = f"export-1.user-1.{int(time.time()) - 10}"
    assert verify_download(expired + ".deadbeef") is None


def test_rate_limit_blocks_a_burst_of_messages(client):
    """The chat limiter must actually fire - it is the abuse control on the API."""
    from app.core import ratelimit
    from app.core.config import settings

    headers = authenticate(client, "client@example.com")
    structures = client.get(f"{API}/structures", headers=headers).json()
    session_id = client.post(
        f"{API}/sessions", headers=headers, json={"structure_id": structures[0]["id"]}
    ).json()["state"]["id"]

    allowed = ratelimit.Rule.parse(settings.RL_CHAT).limit
    statuses = [
        client.post(
            f"{API}/sessions/{session_id}/messages", headers=headers,
            json={"message": f"Reponse numero {i}."},
        ).status_code
        for i in range(allowed + 3)
    ]

    assert 429 in statuses, "the burst should have been throttled"
    assert statuses.index(429) > allowed - 2, "throttled far too early"

    blocked = client.post(
        f"{API}/sessions/{session_id}/messages", headers=headers, json={"message": "encore"}
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_a_locked_account_is_told_so_when_the_password_is_right(client):
    """A generic refusal for a locked account sends a legitimate user into a
    retry loop with no idea why. Once they have proved they hold the password,
    naming the lockout reveals nothing they do not already know."""
    import datetime as dt

    from sqlalchemy import select

    from app.db.models import User, utcnow
    from app.db.session import SessionLocal

    email = "client@example.com"
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one()
        user.locked_until = utcnow() + dt.timedelta(minutes=12)
        db.commit()
    try:
        right = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
        assert right.status_code == 423
        assert "verrouill" in right.json()["detail"].lower()
        assert "minute" in right.json()["detail"].lower()

        # A wrong password on the same locked account stays indistinguishable.
        wrong = client.post(f"{API}/auth/login", json={"email": email, "password": "not-it"})
        assert wrong.status_code == 401
        assert wrong.json()["detail"] == "Identifiants invalides."
    finally:
        with SessionLocal() as db:
            user = db.execute(select(User).where(User.email == email)).scalar_one()
            user.locked_until = None
            user.failed_attempts = 0
            db.commit()
