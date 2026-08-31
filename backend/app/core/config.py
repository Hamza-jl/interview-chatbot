"""Application configuration.

Secrets are never given defaults: the process refuses to boot without them so a
deployment can not silently fall back to a well-known development key.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _b64key(value: str, name: str, length: int = 32) -> str:
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"{name} must be base64-encoded. Run `python -m app.scripts.genkeys --write`."
        ) from exc
    if len(raw) != length:
        raise ValueError(f"{name} must decode to exactly {length} bytes, got {len(raw)}.")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=True
    )

    ENV: Literal["dev", "staging", "prod"] = "dev"
    APP_NAME: str = "Interview Collect"
    API_PREFIX: str = "/api/v1"

    # ---- cryptographic material -------------------------------------------
    MASTER_KEK: str
    JWT_SECRET: str
    DOWNLOAD_SIGNING_KEY: str

    # ---- token / session lifetimes ----------------------------------------
    ACCESS_TTL_SECONDS: int = 600           # 10 min - kept in memory only
    REFRESH_TTL_SECONDS: int = 43_200       # 12 h absolute cap
    IDLE_TIMEOUT_SECONDS: int = 900         # 15 min of inactivity
    DOWNLOAD_TTL_SECONDS: int = 120         # signed download links

    # ---- authentication hardening ------------------------------------------
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_SECONDS: int = 900
    REQUIRE_TOTP: bool = True
    MIN_PASSWORD_LENGTH: int = 12

    # ---- rate limiting (requests / window seconds) -------------------------
    RL_LOGIN: str = "10/300"
    RL_CHAT: str = "40/60"
    RL_EXPORT: str = "5/300"
    RL_GLOBAL: str = "300/60"

    # ---- storage ------------------------------------------------------------
    DATABASE_URL: str = "sqlite+pysqlite:///./var/pca.db"
    TEMPLATE_DIR: str = "./templates"
    EXPORT_DIR: str = "./var/exports"
    MAX_BODY_BYTES: int = 256 * 1024

    # ---- transcripts ---------------------------------------------------------
    # A readable log of each interview, one file per entity, rewritten after
    # every turn. Off by default, and for good reason: the database keeps every
    # answer encrypted per field, and these files are PLAINTEXT on disk. Turning
    # it on is a deliberate trade of confidentiality for legibility - put the
    # directory somewhere the operating system protects.
    TRANSCRIPT_ENABLED: bool = False
    TRANSCRIPT_DIR: str = "./var/transcripts"

    # ---- LLM ----------------------------------------------------------------
    # "auto" picks Anthropic when a key is present, else a reachable Ollama,
    # else the deterministic engine. Pin it explicitly in production.
    LLM_PROVIDER: Literal["auto", "anthropic", "ollama", "off"] = "auto"

    ANTHROPIC_API_KEY: str = ""
    LLM_MODEL: str = "claude-opus-5"
    LLM_MAX_TOKENS: int = 4000
    LLM_EFFORT: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # ---- Local inference (Ollama) --------------------------------------------
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT: int = 120
    OLLAMA_NUM_CTX: int = 8192

    # ---- web ----------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173"
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str = ""

    # ---- deployment identity -------------------------------------------------
    # These appear in the assistant's own words and in the generated document.
    # Set them per deployment; nothing about the client is hard-coded.
    CLIENT_NAME: str = "votre organisation"
    PROGRAMME_LABEL: str = ""          # e.g. "les projets de continuite"
    CONSULTING_ORG: str = "l'equipe PCA"
    DOC_REFERENCE_PREFIX: str = "EDL"  # document reference: EDL-<code>-V1.0

    # Domain separator for every AAD and token issuer. Changing it on a live
    # deployment makes existing ciphertexts unreadable - pin the original value
    # in .env when upgrading rather than accepting a new default.
    CRYPTO_NAMESPACE: str = "interview-collect"

    # ---- closing card --------------------------------------------------------
    CONTACT_NAME: str = "Équipe PCA"
    CONTACT_EMAIL: str = "pca@example.com"
    CONTACT_PHONE: str = ""          # empty hides the line entirely

    @field_validator("MASTER_KEK")
    @classmethod
    def _kek(cls, v: str) -> str:
        return _b64key(v, "MASTER_KEK")

    @field_validator("JWT_SECRET")
    @classmethod
    def _jwt(cls, v: str) -> str:
        # HS512 keys should match the digest size - RFC 7518 section 3.2.
        return _b64key(v, "JWT_SECRET", length=64)

    @field_validator("DOWNLOAD_SIGNING_KEY")
    @classmethod
    def _dl(cls, v: str) -> str:
        return _b64key(v, "DOWNLOAD_SIGNING_KEY")

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def kek_bytes(self) -> bytes:
        return base64.b64decode(self.MASTER_KEK)

    @property
    def jwt_bytes(self) -> bytes:
        return base64.b64decode(self.JWT_SECRET)

    @property
    def download_key_bytes(self) -> bytes:
        return base64.b64decode(self.DOWNLOAD_SIGNING_KEY)

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
