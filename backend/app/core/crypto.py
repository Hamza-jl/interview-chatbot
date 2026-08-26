"""Envelope encryption for client-supplied content.

Threat model
------------
Every answer an interviewee types is treated as confidential
material.  Nothing sensitive is ever written to the database in cleartext.

Layers
------
1. A **master KEK** (32 bytes) lives only in the process environment / KMS.
2. Every survey session gets its own random **DEK** (32 bytes).  The DEK is
   stored only in wrapped form (AES-256-GCM under the KEK).
3. Every individual field is sealed with AES-256-GCM under the session DEK,
   with the field's logical address bound in as **additional authenticated
   data**.  Moving a ciphertext from one field (or one session) to another is
   therefore detected and rejected - not merely undecryptable garbage.

Rotating the KEK only requires re-wrapping the per-session DEKs, never
re-encrypting the field corpus.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_BYTES = 12
DEK_BYTES = 32
_KEK_AAD = f"{settings.CRYPTO_NAMESPACE}/dek-wrap/v1".encode()


class DecryptionError(RuntimeError):
    """Raised when a ciphertext fails authentication (tampering or misbinding)."""


# --------------------------------------------------------------------------- #
# Data-encryption keys
# --------------------------------------------------------------------------- #
def new_dek() -> bytes:
    return secrets.token_bytes(DEK_BYTES)


def wrap_dek(dek: bytes) -> str:
    """Seal a session DEK under the master KEK. Returns base64(nonce || ct)."""
    if len(dek) != DEK_BYTES:
        raise ValueError("DEK must be 32 bytes")
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(settings.kek_bytes).encrypt(nonce, dek, _KEK_AAD)
    return base64.b64encode(nonce + ct).decode()


def unwrap_dek(wrapped: str) -> bytes:
    blob = base64.b64decode(wrapped)
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(settings.kek_bytes).decrypt(nonce, ct, _KEK_AAD)
    except InvalidTag as exc:
        raise DecryptionError("session key could not be unwrapped") from exc


# --------------------------------------------------------------------------- #
# Field-level sealing
# --------------------------------------------------------------------------- #
def _aad(session_id: str, field: str) -> bytes:
    """Bind a ciphertext to exactly one (session, field) address."""
    return f"{settings.CRYPTO_NAMESPACE}/v1|{session_id}|{field}".encode()


def seal(dek: bytes, session_id: str, field: str, plaintext: str) -> str:
    nonce = os.urandom(NONCE_BYTES)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), _aad(session_id, field))
    return base64.b64encode(nonce + ct).decode()


def open_sealed(dek: bytes, session_id: str, field: str, blob: str) -> str:
    raw = base64.b64decode(blob)
    nonce, ct = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
    try:
        return AESGCM(dek).decrypt(nonce, ct, _aad(session_id, field)).decode("utf-8")
    except InvalidTag as exc:
        raise DecryptionError(f"ciphertext for '{field}' failed authentication") from exc


def seal_json(dek: bytes, session_id: str, field: str, obj: Any) -> str:
    return seal(dek, session_id, field, json.dumps(obj, ensure_ascii=False, sort_keys=True))


def open_json(dek: bytes, session_id: str, field: str, blob: str) -> Any:
    return json.loads(open_sealed(dek, session_id, field, blob))


# --------------------------------------------------------------------------- #
# Server-side secrets that are not session-scoped (e.g. TOTP seeds)
# --------------------------------------------------------------------------- #
_VAULT_AAD = f"{settings.CRYPTO_NAMESPACE}/vault/v1".encode()


def vault_seal(plaintext: str, label: str) -> str:
    nonce = os.urandom(NONCE_BYTES)
    aad = _VAULT_AAD + b"|" + label.encode()
    ct = AESGCM(settings.kek_bytes).encrypt(nonce, plaintext.encode(), aad)
    return base64.b64encode(nonce + ct).decode()


def vault_open(blob: str, label: str) -> str:
    raw = base64.b64decode(blob)
    aad = _VAULT_AAD + b"|" + label.encode()
    try:
        return AESGCM(settings.kek_bytes).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad).decode()
    except InvalidTag as exc:
        raise DecryptionError(f"vault item '{label}' failed authentication") from exc


def encrypt_bytes(dek: bytes, session_id: str, field: str, data: bytes) -> bytes:
    """Seal binary payloads (generated .docx) - returns nonce || ciphertext."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(dek).encrypt(nonce, data, _aad(session_id, field))


def decrypt_bytes(dek: bytes, session_id: str, field: str, blob: bytes) -> bytes:
    try:
        return AESGCM(dek).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], _aad(session_id, field))
    except InvalidTag as exc:
        raise DecryptionError("export payload failed authentication") from exc
