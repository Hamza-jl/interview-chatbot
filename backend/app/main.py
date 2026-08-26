"""ASGI application factory."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, auth, chat, survey
from app.core.config import settings
from app.core.middleware import (
    BodyLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
)
from app.db.session import init_db

logger = logging.getLogger("pca.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    init_db()
    from app.ai.llm import active_backend, active_label

    backend = active_backend()
    logger.info(
        "%s ready | env=%s | provider=%s | moteur=%s",
        settings.APP_NAME,
        settings.ENV,
        backend.name if backend else "aucun",
        active_label(),
    )
    if settings.is_prod and not settings.COOKIE_SECURE:
        logger.error("COOKIE_SECURE is false in production - refresh cookies would travel in clear")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Collecte assistee d'un etat des lieux, restitue dans le modele Word du client.",
        lifespan=lifespan,
        # The interactive docs are an information-disclosure surface in production.
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )
    app.state.trust_proxy = settings.is_prod

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,   # explicit allow-list, never "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "X-Content-Digest"],
        max_age=600,
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        # Echoing the offending payload back would reflect confidential input.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Requete invalide.", "fields": [
                ".".join(str(p) for p in err.get("loc", [])[1:]) for err in exc.errors()
            ][:10]},
        )

    api = settings.API_PREFIX
    app.include_router(auth.router, prefix=api)
    app.include_router(survey.router, prefix=api)
    app.include_router(chat.router, prefix=api)
    app.include_router(admin.router, prefix=api)

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "env": settings.ENV}

    return app


app = create_app()
