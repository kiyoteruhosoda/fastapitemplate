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

    コンテキスト固有モデルを追加したらここへ import を足し、``_registered`` にも並べる。

    ⚠ **import しただけでは ``ruff --fix`` に消される。** モデルは import の副作用で
    ``Base.metadata`` へ登録されるので「使っていない import」に見え、F401 として
    1 行ずつ剥がされる。消えても起動もテストも通ってしまい、気付けるのは
    ``alembic revision --autogenerate`` が**全テーブルの削除を提案したとき**になる。
    参照して使うことで、消せない形にしてある。
    """
    from bounded_contexts.account_security.infrastructure import account_security_models
    from bounded_contexts.audit.infrastructure import audit_log_model
    from bounded_contexts.example.infrastructure import item_model
    from bounded_contexts.identity_federation.infrastructure import identity_federation_models
    from shared.infrastructure import models as shared_models
    from shared.kernel.database.db import Base

    _registered = (
        account_security_models,
        audit_log_model,
        item_model,
        identity_federation_models,
        shared_models,
    )
    if not _registered:  # pragma: no cover - 参照して import を消させないための行
        raise RuntimeError("no models registered")

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
