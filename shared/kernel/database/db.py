"""SQLAlchemy 基盤（DeclarativeBase とエンジン管理）。

モデルは :class:`Base` を継承する。エンジンは ``settings.database_uri`` から
遅延生成し、テストでは :func:`set_engine` で SQLite in-memory へ差し替える。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """全 SQLAlchemy モデルの基底クラス。"""


_engine: sa.Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> sa.Engine:
    global _engine
    if _engine is None:
        from shared.kernel.settings.settings import settings

        url = settings.database_uri
        if not url:
            raise RuntimeError("DATABASE_URI が設定されていません。環境変数を確認してください。")
        kwargs: dict[str, object] = {}
        if not url.startswith("sqlite"):
            kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}
        _engine = sa.create_engine(url, **kwargs)
    return _engine


def set_engine(engine: sa.Engine | None) -> None:
    """エンジンを差し替える（テスト用）。``None`` でリセット。"""
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
