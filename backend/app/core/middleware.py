"""HTTP hardening: security headers, body caps, request ids, log redaction."""
from __future__ import annotations

import logging
import re
import time
import uuid

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger("pca.http")

# The API serves JSON only; the CSP is therefore maximally restrictive. The SPA
# is served by its own origin (nginx / Vite) which ships an equivalent policy.
CSP = "; ".join(
    [
        "default-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "sandbox",
    ]
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        headers = response.headers
        headers["Content-Security-Policy"] = CSP
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Resource-Policy"] = "same-site"
        headers["X-Permitted-Cross-Domain-Policies"] = "none"
        # Confidential banking content must never sit in a shared cache.
        headers.setdefault("Cache-Control", "no-store, no-cache, must-revalidate, private")
        headers.setdefault("Pragma", "no-cache")
        if settings.is_prod:
            headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        if "server" in headers:
            del headers["server"]
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches a request id and logs timing - never the payload."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error rid=%s path=%s", request_id, request.url.path)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Erreur interne.", "request_id": request_id},
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s in %.1fms rid=%s",
            request.method, request.url.path, response.status_code, elapsed_ms, request_id,
        )
        return response


class BodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,  # Content Too Large
                content={"detail": "Charge utile trop volumineuse."},
            )
        return await call_next(request)


# --------------------------------------------------------------------------- #
# Log redaction
# --------------------------------------------------------------------------- #
_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"),
    (re.compile(r"\b\d{6}\b"), "<otp>"),
    (re.compile(r"\b(?:\d[ -]?){12,19}\b"), "<pan>"),
    (re.compile(r"(?i)(authorization|bearer|token|password|secret)[\"'\s:=]+\S+"), r"\1=<redacted>"),
]


class RedactingFilter(logging.Filter):
    """Last line of defence: scrubs identifiers that slip into a log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = message
        for pattern, replacement in _PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s :: %(message)s"))
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO if settings.is_prod else logging.DEBUG)
    for noisy in ("uvicorn.access", "httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
