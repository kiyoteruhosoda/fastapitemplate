"""SQLAlchemy foundation (DeclarativeBase and engine management).

Models inherit from :class:`Base`. The engine is created lazily from ``settings.database_uri``,
and tests replace it with in-memory SQLite via :func:`set_engine`.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class of all SQLAlchemy models."""


_engine: sa.Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> sa.Engine:
    global _engine
    if _engine is None:
        from shared.kernel.settings.settings import settings

        url = settings.database_uri
        if not url:
            raise RuntimeError("DATABASE_URI is not set. Check the environment variables.")
        kwargs: dict[str, object] = {}
        if not url.startswith("sqlite"):
            kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}
        _engine = sa.create_engine(url, **kwargs)
    return _engine


def set_engine(engine: sa.Engine | None) -> None:
    """Replace the engine (for tests). ``None`` resets it."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = None


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


__all__ = ["Base", "get_engine", "get_session_factory", "set_engine"]
