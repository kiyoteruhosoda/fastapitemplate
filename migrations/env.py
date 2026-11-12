"""Alembic migration environment (plain Alembic + SQLAlchemy).

Usage::

    uv run alembic revision --autogenerate -m "description"
    uv run alembic upgrade head
    uv run alembic downgrade -1

The database is given by the ``DATABASE_URI`` environment variable (or ``.env``).
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
    """Import all models and return the MetaData.

    When adding a context-specific model, add its import here and also list it in ``_registered``.

    ⚠ **A bare import gets removed by ``ruff --fix``.** Models register themselves in
    ``Base.metadata`` as an import side effect, so the imports look "unused" and are stripped one
    line at a time as F401. Startup and tests still pass without them; the only sign is
    ``alembic revision --autogenerate`` **proposing to drop every table**.
    Referencing them makes them impossible to remove.
    """
    from bounded_contexts.account_security.infrastructure import account_security_models
    from bounded_contexts.audit.infrastructure import audit_log_model
    from bounded_contexts.content_settings.infrastructure import content_setting_model
    from bounded_contexts.example.infrastructure import item_model
    from bounded_contexts.identity_federation.infrastructure import identity_federation_models
    from bounded_contexts.notes.infrastructure import note_model
    from bounded_contexts.notification.infrastructure import notification_models
    from shared.infrastructure import models as shared_models
    from shared.kernel.database.db import Base

    _registered = (
        account_security_models,
        audit_log_model,
        content_setting_model,
        item_model,
        identity_federation_models,
        note_model,
        notification_models,
        shared_models,
    )
    if not _registered:  # pragma: no cover - this line references the imports so they cannot be removed
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
