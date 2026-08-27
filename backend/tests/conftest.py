"""Test harness.

Each run gets a throwaway SQLite database and its own cryptographic material,
so tests never touch a real deployment and never depend on seeded state.
"""
from __future__ import annotations

import base64
import os
import secrets
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="interview-collect-tests-")

os.environ.update(
    ENV="dev",
    MASTER_KEK=base64.b64encode(secrets.token_bytes(32)).decode(),
    JWT_SECRET=base64.b64encode(secrets.token_bytes(64)).decode(),
    DOWNLOAD_SIGNING_KEY=base64.b64encode(secrets.token_bytes(32)).decode(),
    DATABASE_URL=f"sqlite+pysqlite:///{Path(_TMP, 'test.db').as_posix()}",
    EXPORT_DIR=str(Path(_TMP, "exports")),
    TEMPLATE_DIR=str(ROOT / "templates"),
    # Pinned off: the suite must not reach a model. It exercises the
    # deterministic engine, so it stays fast, offline and reproducible even on
    # a machine where Ollama happens to be running.
    LLM_PROVIDER="off",
    ANTHROPIC_API_KEY="",
    CORS_ORIGINS="http://localhost:5173",
    # Pinned so the suite does not inherit whatever identity the developer's
    # own .env happens to carry.
    APP_NAME="Interview Collect",
    CLIENT_NAME="Organisation",
    PROGRAMME_LABEL="",
    CONSULTING_ORG="Equipe PCA",
    DOC_REFERENCE_PREFIX="EDL",
    CRYPTO_NAMESPACE="interview-collect-tests",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core import security  # noqa: E402
from app.db.models import Structure, User  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
PASSWORD = "Zephyr!Kadence7#Vlt"


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def seeded() -> dict:
    init_db()
    with SessionLocal() as db:
        if not db.execute(select(Structure)).scalars().first():
            db.add(Structure(code="DSI", name="Direction des Systemes d'Information",
                             parent="Direction Generale", template_kind="dsi"))
            db.add(Structure(code="DCR", name="Direction du Credit",
                             parent="DGA", template_kind="entite"))
            db.add(Structure(code="DRH", name="Direction des Ressources Humaines",
                             parent="DG", template_kind="entite"))
        db.add(User(email="client@example.com", full_name="Nadia Ben Youssef",
                    organisation="Organisation", role="client",
                    password_hash=security.hash_password(PASSWORD),
                    must_change_password=False, allowed_structures="DSI"))
        db.add(User(email="staff@example.org", full_name="Consultant Devoteam",
                    organisation="Devoteam", role="admin",
                    password_hash=security.hash_password(PASSWORD),
                    must_change_password=False))
        db.commit()
    return {"password": PASSWORD}


@pytest.fixture(autouse=True)
def fresh_interviews(seeded):
    """Drop every interview between tests.

    The API deliberately *resumes* an unfinished interview for the same
    (user, structure) pair, so without this each test would inherit the previous
    one's cursor. Answers, messages and exports cascade away with the session.
    """
    from app.core import ratelimit
    from app.db.models import SurveySession
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        for survey in db.execute(select(SurveySession)).scalars():
            db.delete(survey)
        db.commit()

    # Counters are per-process and would otherwise accumulate across the whole
    # suite until an unrelated test trips a limit. The limiter itself is covered
    # explicitly by test_rate_limit_blocks_a_burst_of_messages.
    ratelimit.store._buckets.clear()
    yield


_SESSIONS: dict[str, dict] = {}


def authenticate(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    """Complete the password + TOTP dance once per account, then reuse the session.

    Logging in per test would trip the login rate limiter, which is exactly what
    it is there for - the whole suite shares a single client address.
    """
    if email in _SESSIONS:
        return _SESSIONS[email]
    headers = _login(client, email, password)
    _SESSIONS[email] = headers
    return headers


def _login(client: TestClient, email: str, password: str) -> dict:
    import pyotp

    res = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    body = res.json()

    if body["stage"] == "authenticated":
        session = body["session"]
    else:
        challenge = body["challenge"]
        if body["stage"] == "totp_enrollment":
            enroll = client.post(f"{API}/auth/totp/enroll", json={"challenge": challenge})
            assert enroll.status_code == 200, enroll.text
            secret = enroll.json()["secret"]
            res = client.post(
                f"{API}/auth/totp/activate",
                json={"challenge": challenge, "code": pyotp.TOTP(secret).now()},
            )
        else:
            raise AssertionError("unexpected stage for a fresh account")
        assert res.status_code == 200, res.text
        session = res.json()

    return {
        "Authorization": f"Bearer {session['access_token']}",
        "X-CSRF-Token": session["csrf_token"],
    }


def say(client: TestClient, headers: dict, session_id: str, message: str) -> dict:
    """One conversational turn. Returns the raw ChatResponse."""
    res = client.post(
        f"{API}/sessions/{session_id}/messages", headers=headers, json={"message": message}
    )
    assert res.status_code == 200, res.text
    return res.json()


def confirm(client: TestClient, headers: dict, session_id: str, pending: dict,
            value: str | None = None, rows: list | None = None) -> dict:
    """Validate a draft, optionally editing it the way the panel would."""
    body = {"question_id": pending["question_id"]}
    if pending["kind"] == "grid":
        body["rows"] = rows if rows is not None else pending.get("rows") or []
    else:
        body["value"] = value if value is not None else pending.get("value") or ""
    res = client.post(f"{API}/sessions/{session_id}/confirm", headers=headers, json=body)
    assert res.status_code == 200, res.text
    return res.json()


def answer(client: TestClient, headers: dict, session_id: str, message: str) -> dict:
    """Answer and confirm in one go - the common path in tests.

    Answers are drafts until confirmed, so a test that only posts a message
    would leave the interview parked on the same question.
    """
    turn = say(client, headers, session_id, message)
    if turn.get("pending"):
        return confirm(client, headers, session_id, turn["pending"])
    return turn


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
# The two .docx files are the client's own documents and are not committed, so a
# fresh clone has no templates. Everything that does not touch them still runs.
TEMPLATES_PRESENT = all(
    (ROOT / "templates" / name).exists()
    for name in ("etat_des_lieux_dsi.docx", "etat_des_lieux_entite.docx")
)

needs_templates = pytest.mark.skipif(
    not TEMPLATES_PRESENT,
    reason="Word templates not present - see backend/templates/README.md",
)


def unaccented(text: str) -> str:
    """Fold accents so assertions survive edits to the French copy."""
    import unicodedata

    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in folded if not unicodedata.combining(c))
