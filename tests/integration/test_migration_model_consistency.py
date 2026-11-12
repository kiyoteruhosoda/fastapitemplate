"""Detecting drift between model definitions and Alembic migrations.

Compares, on SQLite, the schema built by ``alembic upgrade head`` with the one built from the
SQLAlchemy models (``Base.metadata``). Changing a model without adding a migration fails this test.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import bounded_contexts.account_security.infrastructure.account_security_models
import bounded_contexts.audit.infrastructure.audit_log_model
import bounded_contexts.example.infrastructure.item_model  # noqa: F401
import shared.infrastructure.models  # noqa: F401
from shared.kernel.database.db import Base

_INTERNAL_TABLES = {"alembic_version"}


def _schema_snapshot(engine: sa.Engine) -> dict[str, dict[str, dict[str, object]]]:
    inspector = inspect(engine)
    snapshot: dict[str, dict[str, dict[str, object]]] = {}
    for table in inspector.get_table_names():
        if table in _INTERNAL_TABLES:
            continue
        snapshot[table] = {
            column["name"]: {
                "type": str(column["type"]).upper(),
                "nullable": column["nullable"],
            }
            for column in inspector.get_columns(table)
        }
    return snapshot


@pytest.fixture
def migrated_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sa.Engine]:
    db_path = tmp_path / "migrated.db"
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{db_path}")
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    yield engine
    engine.dispose()


def test_migrations_match_models(migrated_engine: sa.Engine, tmp_path: Path) -> None:
    model_engine = create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(model_engine)

    migrated = _schema_snapshot(migrated_engine)
    from_models = _schema_snapshot(model_engine)
    model_engine.dispose()

    assert set(migrated) == set(from_models), "Table sets differ. A model change requires adding a migration."
    for table in from_models:
        assert migrated[table] == from_models[table], (
            f"Column definitions of table {table} differ between the models and the migrations."
        )
