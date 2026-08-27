"""Authentication: password -> TOTP -> rotating refresh session."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.core import audit, ratelimit, security
from app.core.config import settings
from app.core.crypto import vault_open, vault_seal
from app.db.models import AuthSession, RefreshToken, User, utcnow
from app.db.session import get_db
from app.schemas.api import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    TokenResponse,
    TotpActivateRequest,
    TotpEnrollRequest,
    TotpEnrollResponse,
    TotpRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately identical for unknown accounts, wrong passwords and wrong codes.
_GENERIC = "Identifiants invalides."


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        organisation=user.organisation,
        role=user.role,
        must_change_password=user.must_change_password,
        totp_enabled=user.totp_enabled,
    )


def _is_locked(user: User) -> bool:
    if user.locked_until is None:
        return False
    locked_until = deps._aware(user.locked_until)
    return locked_until > utcnow()


def _register_failure(db: Session, user: Optional[User]) -> None:
    if user is None:
        return
    user.failed_attempts += 1
    if user.failed_attempts >= settings.MAX_FAILED_LOGINS:
        user.locked_until = utcnow() + dt.timedelta(seconds=settings.LOCKOUT_SECONDS)
        user.failed_attempts = 0
    db.commit()


def _start_session(
    db: Session, request: Request, response: Response, user: User
) -> TokenResponse:
    """Create the browser session, its first refresh token, and the CSRF pair."""
    ip = ratelimit.client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    auth_session = AuthSession(
        user_id=user.id,
        absolute_expiry=utcnow() + dt.timedelta(seconds=settings.REFRESH_TTL_SECONDS),
        ip_fp=security.pseudonymize(ip),
        ua_fp=security.pseudonymize(user_agent),
    )
    db.add(auth_session)
    db.flush()

    raw_refresh, digest = security.new_refresh_token()
    db.add(
        RefreshToken(
            auth_session_id=auth_session.id,
            token_hash=digest,
            expires_at=auth_session.absolute_expiry,
        )
    )

    user.last_login_at = utcnow()
    user.failed_attempts = 0
    user.locked_until = None

    access, ttl = security.issue_access_token(user.id, user.role, auth_session.id)
    csrf = security.csrf_token(auth_session.id)

    audit.record(
        db, action="auth.login", actor_id=user.id, target=auth_session.id,
        ip=ip, user_agent=user_agent,
    )
    db.commit()

    deps.set_auth_cookies(response, raw_refresh, csrf)
    ratelimit.clear("login", user.email.lower())
    return TokenResponse(access_token=access, expires_in=ttl, csrf_token=csrf, user=_user_out(user))


# --------------------------------------------------------------------------- #
# Step 1 - password
# --------------------------------------------------------------------------- #
@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    email = payload.email.lower().strip()
    ratelimit.enforce(request, "login", settings.RL_LOGIN)
    ratelimit.enforce(request, "login-account", settings.RL_LOGIN, subject=email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    ip = ratelimit.client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    # Runs Argon2 even when the account does not exist, so timing does not leak.
    password_ok = security.verify_password(user.password_hash if user else None, payload.password)

    locked = user is not None and _is_locked(user)
    if user is None or not password_ok or not user.is_active or locked:
        audit.record(
            db, action="auth.login", actor_id=user.id if user else None, target=email,
            outcome="locked" if locked else "denied", ip=ip, user_agent=user_agent,
        )
        db.commit()
        # A wrong password counts against the account; a lockout does not extend itself.
        if user is not None and not password_ok and not locked:
            _register_failure(db, user)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(payload.password)
        db.commit()

    if settings.REQUIRE_TOTP and not user.totp_enabled:
        audit.record(db, action="auth.totp_enrollment_required", actor_id=user.id, ip=ip)
        db.commit()
        return LoginResponse(
            stage="totp_enrollment", challenge=security.issue_challenge(user.id, "enroll")
        )

    if user.totp_enabled:
        audit.record(db, action="auth.password_ok", actor_id=user.id, ip=ip)
        db.commit()
        return LoginResponse(
            stage="totp_required", challenge=security.issue_challenge(user.id, "totp")
        )

    return LoginResponse(stage="authenticated", session=_start_session(db, request, response, user))


# --------------------------------------------------------------------------- #
# Step 2 - one-time code
# --------------------------------------------------------------------------- #
@router.post("/totp", response_model=TokenResponse)
def verify_totp(
    payload: TotpRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ratelimit.enforce(request, "totp", settings.RL_LOGIN)

    user_id = security.read_challenge(payload.challenge, "totp")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    user = db.get(User, user_id)
    if user is None or not user.is_active or not user.totp_enabled or _is_locked(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    ratelimit.enforce(request, "totp-account", "6/300", subject=user.id)
    secret = vault_open(user.totp_secret_enc or "", f"totp:{user.id}")

    if not security.totp_valid(secret, payload.code):
        if not _consume_recovery_code(db, user, payload.code):
            audit.record(
                db, action="auth.totp", actor_id=user.id, outcome="denied",
                ip=ratelimit.client_ip(request),
            )
            _register_failure(db, user)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    return _start_session(db, request, response, user)


def _consume_recovery_code(db: Session, user: User, code: str) -> bool:
    if not user.recovery_codes_enc:
        return False
    digests = json.loads(vault_open(user.recovery_codes_enc, f"recovery:{user.id}"))
    candidate = hashlib.sha256(code.strip().lower().encode()).hexdigest()
    if candidate not in digests:
        return False
    digests.remove(candidate)
    user.recovery_codes_enc = vault_seal(json.dumps(digests), f"recovery:{user.id}")
    audit.record(db, action="auth.recovery_code_used", actor_id=user.id)
    db.commit()
    return True


# --------------------------------------------------------------------------- #
# TOTP enrolment
# --------------------------------------------------------------------------- #
def _qr_svg(uri: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue().decode()


@router.post("/totp/enroll", response_model=TotpEnrollResponse)
def enroll_totp(
    request: Request,
    payload: TotpEnrollRequest | None = None,
    db: Session = Depends(get_db),
) -> TotpEnrollResponse:
    """Callable mid-login (with the enrolment challenge) or by a signed-in user."""
    ratelimit.enforce(request, "enroll", "10/600")

    challenge = payload.challenge if payload else None
    user: Optional[User] = None
    if challenge:
        user_id = security.read_challenge(challenge, "enroll")
        user = db.get(User, user_id) if user_id else None
    else:
        principal = deps.current_principal(request, db, request.headers.get("authorization"))
        user = principal.user

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)
    if user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La double authentification est déjà active.",
        )

    secret = security.new_totp_secret()
    codes = security.new_recovery_codes()

    user.totp_secret_enc = vault_seal(secret, f"totp:{user.id}")
    user.recovery_codes_enc = vault_seal(
        json.dumps([hashlib.sha256(c.encode()).hexdigest() for c in codes]),
        f"recovery:{user.id}",
    )
    audit.record(db, action="auth.totp_enroll_started", actor_id=user.id)
    db.commit()

    uri = security.totp_uri(secret, user.email)
    return TotpEnrollResponse(secret=secret, otpauth_uri=uri, qr_svg=_qr_svg(uri), recovery_codes=codes)


@router.post("/totp/activate", response_model=TokenResponse)
def activate_totp(
    payload: TotpActivateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ratelimit.enforce(request, "enroll", "10/600")

    if not payload.challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge manquant.")
    user_id = security.read_challenge(payload.challenge, "enroll")
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.totp_secret_enc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    secret = vault_open(user.totp_secret_enc, f"totp:{user.id}")
    if not security.totp_valid(secret, payload.code):
        audit.record(db, action="auth.totp_activate", actor_id=user.id, outcome="denied")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Code invalide.")

    user.totp_enabled = True
    audit.record(db, action="auth.totp_activate", actor_id=user.id)
    db.commit()
    return _start_session(db, request, response, user)


# --------------------------------------------------------------------------- #
# Refresh with rotation + reuse detection
# --------------------------------------------------------------------------- #
@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ic_rt: Optional[str] = Cookie(default=None),
) -> TokenResponse:
    ratelimit.enforce(request, "refresh", "60/300")
    if not ic_rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    digest = security.hash_token(ic_rt)
    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == digest)
    ).scalar_one_or_none()

    if record is None:
        deps.clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    auth_session = db.get(AuthSession, record.auth_session_id)
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    # A token that was already exchanged means the cookie leaked: burn the family.
    if record.used_at is not None or auth_session.revoked_at is not None:
        auth_session.revoked_at = auth_session.revoked_at or utcnow()
        auth_session.revoked_reason = "refresh_reuse"
        audit.record(
            db, action="auth.refresh_reuse", actor_id=auth_session.user_id,
            target=auth_session.id, outcome="denied", ip=ratelimit.client_ip(request),
        )
        db.commit()
        deps.clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoquee pour raison de sécurité. Merci de vous reconnecter.",
        )

    if deps._aware(record.expires_at) < utcnow() or deps._aware(auth_session.absolute_expiry) < utcnow():
        deps.clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expiree.")

    user = db.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC)

    raw_next, next_digest = security.new_refresh_token()
    successor = RefreshToken(
        auth_session_id=auth_session.id,
        token_hash=next_digest,
        expires_at=auth_session.absolute_expiry,
    )
    db.add(successor)
    db.flush()

    record.used_at = utcnow()
    record.superseded_by = successor.id
    auth_session.last_seen_at = utcnow()

    access, ttl = security.issue_access_token(user.id, user.role, auth_session.id)
    csrf = security.csrf_token(auth_session.id)
    db.commit()

    deps.set_auth_cookies(response, raw_next, csrf)
    return TokenResponse(access_token=access, expires_in=ttl, csrf_token=csrf, user=_user_out(user))


# --------------------------------------------------------------------------- #
# Session management
# --------------------------------------------------------------------------- #
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> Response:
    principal.auth_session.revoked_at = utcnow()
    principal.auth_session.revoked_reason = "logout"
    audit.record(
        db, action="auth.logout", actor_id=principal.id, target=principal.auth_session.id,
        ip=ratelimit.client_ip(request),
    )
    db.commit()
    deps.clear_auth_cookies(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(principal: deps.Principal = Depends(deps.current_principal)) -> UserOut:
    return _user_out(principal.user)


@router.post("/password", response_model=UserOut)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: deps.Principal = Depends(deps.require_csrf),
) -> UserOut:
    ratelimit.enforce(request, "password", "5/600", subject=principal.id)
    user = principal.user

    if not security.verify_password(user.password_hash, payload.current_password):
        audit.record(db, action="auth.password_change", actor_id=user.id, outcome="denied")
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Mot de passe actuel incorrect."
        )

    problems = security.password_problems(payload.new_password, user.email)
    if problems:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=problems)
    if security.verify_password(user.password_hash, payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=["Le nouveau mot de passe doit differer de l'ancien."],
        )

    user.password_hash = security.hash_password(payload.new_password)
    user.must_change_password = False

    # Every other browser session for this account is invalidated.
    for other in db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user.id,
            AuthSession.id != principal.auth_session.id,
            AuthSession.revoked_at.is_(None),
        )
    ).scalars():
        other.revoked_at = utcnow()
        other.revoked_reason = "password_change"

    audit.record(db, action="auth.password_change", actor_id=user.id, ip=ratelimit.client_ip(request))
    db.commit()
    return _user_out(user)
