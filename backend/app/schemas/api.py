"""Request / response contracts. Every inbound string is length-bounded."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TotpRequest(BaseModel):
    challenge: str = Field(min_length=10, max_length=2048)
    code: str = Field(min_length=6, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    csrf_token: str
    user: "UserOut"


class LoginResponse(BaseModel):
    stage: Literal["totp_required", "totp_enrollment", "authenticated"]
    challenge: Optional[str] = None
    session: Optional[TokenResponse] = None


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    organisation: str
    role: str
    must_change_password: bool
    totp_enabled: bool


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class TotpEnrollRequest(BaseModel):
    """Challenge is carried in the body so it never lands in a URL/proxy log."""

    challenge: Optional[str] = Field(default=None, max_length=2048)


class TotpEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str
    recovery_codes: List[str]


class TotpActivateRequest(BaseModel):
    challenge: Optional[str] = None
    code: str = Field(min_length=6, max_length=8)


# --------------------------------------------------------------------------- #
# Structures & sessions
# --------------------------------------------------------------------------- #
class StructureOut(BaseModel):
    id: str
    code: str
    name: str
    parent: Optional[str]
    template_kind: str


class SessionCreateRequest(BaseModel):
    structure_id: str = Field(min_length=8, max_length=64)


class QuestionOut(BaseModel):
    id: str
    kind: str
    section: str
    label: str
    prompt: str
    help: str
    example: str
    columns: List[Dict[str, Any]]
    index: int
    total: int


class ProgressSection(BaseModel):
    title: str
    total: int
    answered: int
    active: bool


class SessionState(BaseModel):
    id: str
    structure: StructureOut
    template_kind: str
    status: str
    cursor: int
    total: int
    answered: int
    percent: int
    question: Optional[QuestionOut]
    sections: List[ProgressSection]
    degraded: bool = False
    engine: str = ""   # which model produced the last turn


class MessageOut(BaseModel):
    id: str
    role: str
    body: str
    intent: Optional[str] = None
    created_at: str


class SessionDetail(BaseModel):
    state: SessionState
    messages: List[MessageOut]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class PendingAnswer(BaseModel):
    """What the engine extracted, laid out for the verification panel.

    Self-contained on purpose: it carries its own question metadata so the panel
    keeps rendering the right table even as the interview moves on.
    """

    question_id: str
    label: str
    section: str
    kind: str                       # field | open | grid
    prompt: str = ""
    help: str = ""
    example: str = ""
    columns: List[Dict[str, Any]] = Field(default_factory=list)
    value: Optional[str] = None
    rows: Optional[List[Dict[str, str]]] = None


class ConfirmRequest(BaseModel):
    """The payload as the interviewee validated it - edits included."""

    question_id: str = Field(min_length=1, max_length=64)
    value: Optional[str] = Field(default=None, max_length=8000)
    rows: Optional[List[Dict[str, str]]] = None


class ChatResponse(BaseModel):
    reply: MessageOut
    state: SessionState
    intent: str
    recorded: bool
    completed: bool = False
    # Set when an extraction is waiting for the interviewee to verify it.
    # While this is present the interview does not advance.
    pending: Optional[PendingAnswer] = None


class AnswerOverride(BaseModel):
    """Manual correction from the review panel - bypasses the model entirely."""

    question_id: str = Field(min_length=1, max_length=64)
    value: Optional[str] = Field(default=None, max_length=8000)
    rows: Optional[List[Dict[str, str]]] = None


class AnswerOut(BaseModel):
    question_id: str
    label: str
    section: str
    kind: str
    completeness: str
    confirmed: bool = False
    value: Optional[str] = None
    rows: Optional[List[Dict[str, str]]] = None


class ExportOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    sha256: str
    created_at: str
    download_token: str


class ContactCard(BaseModel):
    name: str
    email: str
    phone: str


TokenResponse.model_rebuild()
