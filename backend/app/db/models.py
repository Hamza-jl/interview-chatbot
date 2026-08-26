"""Persistence layer.

Nothing an interviewee typed is stored in a readable column: chat
turns, extracted answers and generated documents are all sealed by
``app.core.crypto`` before they reach these tables.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def uid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    organisation: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="client")  # client|analyst|admin

    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)

    totp_secret_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_codes_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # A client account is scoped to the entities it is allowed to document.
    allowed_structures: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # csv of codes


class AuthSession(Base):
    """One browser login. Owns a rotating family of refresh tokens."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    absolute_expiry: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    ip_fp: Mapped[str] = mapped_column(String(32), default="")
    ua_fp: Mapped[str] = mapped_column(String(32), default="")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    auth_session_id: Mapped[str] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


# --------------------------------------------------------------------------- #
# Survey domain
# --------------------------------------------------------------------------- #
class Structure(Base):
    """An organisational entity of the bank (a DSI, a business direction, ...)."""

    __tablename__ = "structures"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    parent: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    template_kind: Mapped[str] = mapped_column(String(16), default="entite")  # dsi|entite
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SurveySession(Base):
    """One interview: a user documenting one structure with one template."""

    __tablename__ = "survey_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    structure_id: Mapped[str] = mapped_column(ForeignKey("structures.id"), index=True)
    template_kind: Mapped[str] = mapped_column(String(16))

    status: Mapped[str] = mapped_column(String(16), default="in_progress")  # in_progress|completed
    cursor: Mapped[int] = mapped_column(Integer, default=0)      # index into the question plan
    followups: Mapped[int] = mapped_column(Integer, default=0)   # consecutive re-asks on cursor

    wrapped_dek: Mapped[str] = mapped_column(Text)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_activity_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    structure: Mapped[Structure] = relationship(lazy="joined")

    __table_args__ = (Index("ix_survey_user_status", "user_id", "status"),)


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("survey_sessions.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))          # field|open|grid
    payload_enc: Mapped[str] = mapped_column(Text)          # sealed JSON
    completeness: Mapped[str] = mapped_column(String(12), default="complete")
    # An answer is a *draft* until the interviewee has seen it laid out in the
    # verification panel and confirmed it. Only confirmed answers count towards
    # progress and only confirmed answers reach the generated document, so no
    # extraction can land in a client deliverable unreviewed.
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_answer_slot"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("survey_sessions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(12))           # user|assistant
    body_enc: Mapped[str] = mapped_column(Text)
    intent: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    question_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_chat_session_seq", "session_id", "seq"),)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("survey_sessions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    blob_path: Mapped[str] = mapped_column(String(500))     # ciphertext on disk
    sha256: Mapped[str] = mapped_column(String(64))         # digest of the *plaintext* docx
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    download_count: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- #
# Tamper-evident audit trail
# --------------------------------------------------------------------------- #
class AuditLog(Base):
    """Append-only. Each row commits to the previous one, forming a hash chain."""

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    target: Mapped[str] = mapped_column(String(120), default="")
    outcome: Mapped[str] = mapped_column(String(12), default="ok")
    ip_fp: Mapped[str] = mapped_column(String(32), default="")
    ua_fp: Mapped[str] = mapped_column(String(32), default="")
    meta: Mapped[str] = mapped_column(Text, default="{}")   # never contains client answers
    prev_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)
    entry_hash: Mapped[str] = mapped_column(String(64))
