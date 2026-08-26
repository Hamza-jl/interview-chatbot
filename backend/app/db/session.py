"""Engine + session factory.

Route handlers are declared with ``def`` (not ``async def``) so FastAPI runs
them in a worker thread; the ORM and the Anthropic client therefore stay fully
synchronous, which removes a whole class of event-loop blocking bugs.
"""
from __future__ import annotations

import logging
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("pca.db")

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine: Engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=FULL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added after the first release. `create_all` never alters an existing
# table, so a pilot database would keep the old shape and every query would
# fail. Alembic is the right answer once this is in production - see
# docs/SECURITY.md - but a pilot should not lose its data to a schema bump.
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("answers", "confirmed", "BOOLEAN NOT NULL DEFAULT 0"),
]

# Run once, immediately after the matching column is created. Rows that already
# existed were recorded under the old flow, where saving *was* the commit - so
# they are confirmed. Without this an existing interview would drop to 0%
# progress and export an empty document.
_BACKFILL: dict[tuple[str, str], str] = {
    ("answers", "confirmed"): "UPDATE answers SET confirmed = 1",
}


def _apply_pending_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            if column in present:
                continue
            logger.info("schema: adding %s.%s", table, column)
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

            backfill = _BACKFILL.get((table, column))
            if backfill:
                result = connection.execute(text(backfill))
                logger.info("schema: backfilled %s row(s) in %s", result.rowcount, table)


def init_db() -> None:
    from app.db import models  # noqa: F401  (registers the mappers)

    models.Base.metadata.create_all(bind=engine)
    _apply_pending_columns()
