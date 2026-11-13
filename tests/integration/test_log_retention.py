"""Deleting expired logs (with real SQL; checks the boundaries of both tables and batching)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from bounded_contexts.audit.infrastructure.sql_expired_log_remover import (
    SqlExpiredLogRemover,
)
from bounded_contexts.audit.presentation.log_retention import purge_expired_logs_once
from shared.infrastructure.models.log import Log
from shared.kernel.timestamps import utcnow

_NOW = datetime(2026, 8, 2, 12, 0, 0)


def _insert_logs(engine: sa.Engine, created_at: list[datetime]) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Log),
            [{"created_at": moment, "level": "INFO", "logger": "app.test", "message": "x"} for moment in created_at],
        )


def _insert_audit_logs(engine: sa.Engine, occurred_at: list[datetime]) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.insert(AuditLogModel),
            [{"occurred_at": moment, "event_type": "login.succeeded", "result": "success"} for moment in occurred_at],
        )


def _remaining(engine: sa.Engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table}")) or 0


def test_only_rows_older_than_the_cutoff_are_deleted(engine: sa.Engine) -> None:
    """The boundary itself is kept (``<``, not ``<=``)."""
    cutoff = _NOW - timedelta(days=30)
    _insert_logs(engine, [cutoff - timedelta(seconds=1), cutoff, cutoff + timedelta(seconds=1)])

    deleted = SqlExpiredLogRemover().delete_application_logs_before(cutoff)

    assert deleted == 1
    assert _remaining(engine, "log") == 2


def test_the_audit_log_is_deleted_by_its_own_timestamp(engine: sa.Engine) -> None:
    """``audit_log`` is judged by ``occurred_at`` (its column name differs from ``log``)."""
    cutoff = _NOW - timedelta(days=365)
    _insert_audit_logs(engine, [cutoff - timedelta(days=1), cutoff + timedelta(days=1)])

    deleted = SqlExpiredLogRemover().delete_audit_logs_before(cutoff)

    assert deleted == 1
    assert _remaining(engine, "audit_log") == 1


def test_deletion_continues_past_one_chunk(engine: sa.Engine) -> None:
    """Even when the targets do not fit in one batch, they are deleted until none remain."""
    old = _NOW - timedelta(days=100)
    _insert_logs(engine, [old] * 7)

    deleted = SqlExpiredLogRemover(chunk_size=2).delete_application_logs_before(_NOW)

    assert deleted == 7
    assert _remaining(engine, "log") == 0


def test_nothing_to_delete_leaves_the_table_alone(engine: sa.Engine) -> None:
    _insert_logs(engine, [_NOW])

    assert SqlExpiredLogRemover().delete_application_logs_before(_NOW - timedelta(days=1)) == 0
    assert _remaining(engine, "log") == 1


def test_the_scheduled_job_deletes_nothing_with_the_default_settings(engine: sa.Engine) -> None:
    """A periodic run with the default settings deletes no rows."""
    ancient = utcnow() - timedelta(days=10_000)
    _insert_logs(engine, [ancient])
    _insert_audit_logs(engine, [ancient])

    purge_expired_logs_once()

    assert _remaining(engine, "log") == 1
    assert _remaining(engine, "audit_log") == 1


def test_the_scheduled_job_uses_the_configured_retention(engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """The configured number of days becomes the cleanup boundary directly (no restart in between)."""
    monkeypatch.setenv("LOG_RETENTION_DAYS", "30")
    now = utcnow()
    _insert_logs(engine, [now - timedelta(days=31), now])
    _insert_audit_logs(engine, [now - timedelta(days=31)])

    purge_expired_logs_once()

    assert _remaining(engine, "log") == 1
    # Audit logs use a separate key, so they are not deleted unless set
    assert _remaining(engine, "audit_log") == 1
