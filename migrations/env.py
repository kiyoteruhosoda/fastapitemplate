"""Alembic マイグレーション環境設定（純粋な Alembic + SQLAlchemy）。

実行方法::

    uv run alembic revision --autogenerate -m "description"
    uv run alembic upgrade head
    uv run alembic downgrade -1

接続先は環境変数 ``DATABASE_URI``（または ``.env``）で指定する。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, create_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _get_database_url() -> str:
    from shared.kernel.settings.settings import settings

    return settings.database_uri


def _load_metadata() -> MetaData:
    """全モデルを import して MetaData を返す。

    コンテキスト固有モデルを追加したらここへ import を足す。
    """
    import bounded_contexts.account_security.infrastructure.account_security_models
    import bounded_contexts.example.infrastructure.item_model  # noqa: F401
    import shared.infrastructure.models  # noqa: F401
    from shared.kernel.database.db import Base

    return Base.metadata


target_metadata = _load_metadata()


def run_migrations_offline() -> None:
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_get_database_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
