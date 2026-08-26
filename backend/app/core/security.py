"""Password hashing, token issuance, TOTP and CSRF primitives."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

# OWASP "second choice" parameters, sized for a server-side login endpoint.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4, hash_len=32, salt_len=16)

# A dummy verification target so that a login attempt against a non-existent
# account costs the same wall-clock time as one against a real account.
_DUMMY_HASH = _hasher.hash("interview-collect-timing-equalizer")

JWT_ALG = "HS512"
_ISS = settings.CRYPTO_NAMESPACE


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: Optional[str], password: str) -> bool:
    """Constant-ish time verification; always runs Argon2 even for unknown users."""
    target = stored_hash or _DUMMY_HASH
    try:
        _hasher.verify(target, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return stored_hash is not None


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


_COMMON = {
    "password", "motdepasse", "azerty", "qwerty", "123456",
    "devoteam", "continuite", "banque", "admin", "welcome",
}


def password_problems(password: str, email: str = "") -> list[str]:
    """Server-side policy. Surfaced to the user only during a password change."""
    problems: list[str] = []
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        problems.append(f"Au moins {settings.MIN_PASSWORD_LENGTH} caracteres.")
    if not re.search(r"[a-z]", password):
        problems.append("Au moins une minuscule.")
    if not re.search(r"[A-Z]", password):
        problems.append("Au moins une majuscule.")
    if not re.search(r"\d", password):
        problems.append("Au moins un chiffre.")
    if not re.search(r"[^\w\s]", password):
        problems.append("Au moins un caractere special.")
    low = password.lower()
    if any(c in low for c in _COMMON):
        problems.append("Mot de passe trop previsible (terme courant detecte).")
    local = email.split("@")[0].lower() if email else ""
    if local and len(local) > 2 and local in low:
        problems.append("Le mot de passe ne doit pas contenir votre identifiant.")
    return problems


# --------------------------------------------------------------------------- #
# Access tokens (short-lived, Authorization header, kept in memory only)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AccessClaims:
    sub: str
    role: str
    sid: str          # auth-session id, ties the access token to a token family
    jti: str
    exp: int


def issue_access_token(user_id: str, role: str, auth_session_id: str) -> tuple[str, int]:
    now = int(time.time())
    exp = now + settings.ACCESS_TTL_SECONDS
    payload: Dict[str, Any] = {
        "iss": _ISS,
        "aud": _ISS,
        "sub": user_id,
        "role": role,
        "sid": auth_session_id,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "nbf": now,
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_bytes, algorithm=JWT_ALG), settings.ACCESS_TTL_SECONDS


def decode_access_token(token: str) -> AccessClaims:
    data = jwt.decode(
        token,
        settings.jwt_bytes,
        algorithms=[JWT_ALG],          # pinned: no "alg: none", no HS/RS confusion
        audience=_ISS,
        issuer=_ISS,
        options={"require": ["exp", "iat", "nbf", "sub", "jti", "aud", "iss"]},
    )
    return AccessClaims(
        sub=data["sub"], role=data["role"], sid=data["sid"], jti=data["jti"], exp=data["exp"]
    )


# --------------------------------------------------------------------------- #
# Two-factor challenge (issued after the password step, before the OTP step)
# --------------------------------------------------------------------------- #
_CHALLENGE_AUD = _ISS + "/2fa"
CHALLENGE_TTL_SECONDS = 300


def issue_challenge(user_id: str, purpose: str = "totp") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": _ISS,
            "aud": _CHALLENGE_AUD,
            "sub": user_id,
            "pur": purpose,
            "jti": uuid.uuid4().hex,
            "iat": now,
            "nbf": now,
            "exp": now + CHALLENGE_TTL_SECONDS,
        },
        settings.jwt_bytes,
        algorithm=JWT_ALG,
    )


def read_challenge(token: str, purpose: str = "totp") -> Optional[str]:
    """Returns the user id, or None if the challenge is invalid or expired."""
    try:
        data = jwt.decode(
            token,
            settings.jwt_bytes,
            algorithms=[JWT_ALG],
            audience=_CHALLENGE_AUD,
            issuer=_ISS,
            options={"require": ["exp", "iat", "nbf", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    return data["sub"] if data.get("pur") == purpose else None


# --------------------------------------------------------------------------- #
# Refresh tokens (opaque, HttpOnly cookie, rotated with reuse detection)
# --------------------------------------------------------------------------- #
def new_refresh_token() -> tuple[str, str]:
    """Returns (clear token, sha256 digest stored in the database)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# CSRF - double submit, HMAC-bound to the auth session
# --------------------------------------------------------------------------- #
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def csrf_token(auth_session_id: str) -> str:
    nonce = secrets.token_urlsafe(16)
    mac = hmac.new(settings.jwt_bytes, f"{auth_session_id}.{nonce}".encode(), hashlib.sha256)
    return f"{nonce}.{_b64u(mac.digest())}"


def csrf_valid(auth_session_id: str, token: Optional[str]) -> bool:
    if not token or "." not in token:
        return False
    nonce, _, sig = token.partition(".")
    expected = hmac.new(
        settings.jwt_bytes, f"{auth_session_id}.{nonce}".encode(), hashlib.sha256
    ).digest()
    return hmac.compare_digest(sig, _b64u(expected))


# --------------------------------------------------------------------------- #
# TOTP
# --------------------------------------------------------------------------- #
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.APP_NAME)


def totp_valid(secret: str, code: str) -> bool:
    if not code or not code.strip().isdigit():
        return False
    # valid_window=1 tolerates one 30s step of clock drift in either direction.
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def new_recovery_codes(n: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


# --------------------------------------------------------------------------- #
# Signed one-shot download tokens
# --------------------------------------------------------------------------- #
def sign_download(export_id: str, user_id: str) -> str:
    exp = int(time.time()) + settings.DOWNLOAD_TTL_SECONDS
    body = f"{export_id}.{user_id}.{exp}"
    mac = hmac.new(settings.download_key_bytes, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def verify_download(token: str) -> Optional[tuple[str, str]]:
    try:
        export_id, user_id, exp_s, mac = token.split(".")
    except ValueError:
        return None
    body = f"{export_id}.{user_id}.{exp_s}"
    expected = hmac.new(settings.download_key_bytes, body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    try:
        if int(exp_s) < int(time.time()):
            return None
    except ValueError:
        return None
    return export_id, user_id


# --------------------------------------------------------------------------- #
# Privacy-preserving request fingerprints for the audit trail
# --------------------------------------------------------------------------- #
def pseudonymize(value: str) -> str:
    """Keyed digest - correlate events without ever storing a raw IP / agent."""
    return hmac.new(settings.jwt_bytes, value.encode(), hashlib.sha256).hexdigest()[:32]
