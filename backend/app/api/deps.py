"""Shared dependencies: authentication, CSRF, roles, cookies."""
from __future__ import annotations

import datetime as dt
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.db.models import AuthSession, User, utcnow
from app.db.session import get_db

REFRESH_COOKIE = "ic_rt"
CSRF_COOKIE = "ic_csrf"

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Session expiree ou invalide.",
    headers={"WWW-Authenticate": "Bearer"},
)


class Principal:
    """The authenticated caller plus the browser session it is bound to."""

    def __init__(self, user: User, auth_session: AuthSession) -> None:
        self.user = user
        self.auth_session = auth_session

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def role(self) -> str:
        return self.user.role


def current_principal(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHORIZED
    token = authorization.split(" ", 1)[1].strip()

    try:
        claims = security.decode_access_token(token)
    except jwt.PyJWTError:
        raise _UNAUTHORIZED

    auth_session = db.get(AuthSession, claims.sid)
    if auth_session is None or auth_session.revoked_at is not None:
        raise _UNAUTHORIZED

    now = utcnow()
    absolute = _aware(auth_session.absolute_expiry)
    last_seen = _aware(auth_session.last_seen_at)
    if absolute < now:
        _revoke(db, auth_session, "absolute_timeout")
        raise _UNAUTHORIZED
    if (now - last_seen).total_seconds() > settings.IDLE_TIMEOUT_SECONDS:
        _revoke(db, auth_session, "idle_timeout")
        raise _UNAUTHORIZED

    user = db.get(User, claims.sub)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED

    auth_session.last_seen_at = now
    db.commit()

    request.state.actor_id = user.id
    return Principal(user, auth_session)


def _aware(value: dt.datetime) -> dt.datetime:
    """SQLite hands datetimes back naive; normalise before comparing."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def _revoke(db: Session, auth_session: AuthSession, reason: str) -> None:
    auth_session.revoked_at = utcnow()
    auth_session.revoked_reason = reason
    db.commit()


def require_password_set(principal: Principal = Depends(current_principal)) -> Principal:
    """Blocks the product surface until a first-login password change is done."""
    if principal.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez definir un nouveau mot de passe avant de continuer.",
        )
    return principal


def require_role(*roles: str):
    def _guard(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acces refuse.")
        return principal

    return _guard


def require_csrf(
    request: Request,
    x_csrf_token: Optional[str] = Header(default=None),
    principal: Principal = Depends(current_principal),
) -> Principal:
    """Double-submit check for any state-changing call that relies on cookies."""
    if not security.csrf_valid(principal.auth_session.id, x_csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Jeton CSRF invalide.")
    return principal


# --------------------------------------------------------------------------- #
# Cookies
# --------------------------------------------------------------------------- #
def set_auth_cookies(response: Response, refresh_token: str, csrf: str) -> None:
    common = {
        "secure": settings.COOKIE_SECURE,
        "samesite": "strict",
        "path": settings.API_PREFIX + "/auth",
    }
    if settings.COOKIE_DOMAIN:
        common["domain"] = settings.COOKIE_DOMAIN

    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        max_age=settings.REFRESH_TTL_SECONDS,
        **common,
    )
    # Readable by the SPA on purpose: it must echo the value back in a header.
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        max_age=settings.REFRESH_TTL_SECONDS,
        **{**common, "path": "/"},
    )


def clear_auth_cookies(response: Response) -> None:
    for name, path in ((REFRESH_COOKIE, settings.API_PREFIX + "/auth"), (CSRF_COOKIE, "/")):
        response.delete_cookie(
            name,
            path=path,
            domain=settings.COOKIE_DOMAIN or None,
            secure=settings.COOKIE_SECURE,
            samesite="strict",
        )


def load_active_session(db: Session, user_id: str, session_id: str):
    """Fetch a survey session, enforcing ownership at the query level."""
    from app.db.models import SurveySession

    stmt = select(SurveySession).where(
        SurveySession.id == session_id, SurveySession.user_id == user_id
    )
    survey = db.execute(stmt).scalar_one_or_none()
    if survey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entretien introuvable.")
    return survey
