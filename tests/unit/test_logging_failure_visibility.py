"""When the logging infrastructure itself fails, it is visible.

If the log writer swallowed exceptions, the only symptoms would be "no logs on the admin screen"
and "saved settings do not take effect", and the cause (no DB connection, before migration, column
mismatch) would be recorded nowhere. This checks **never stopping processing and never staying
silent** at the same time.
"""

from __future__ import annotations

import logging

import pytest

from shared.kernel.logging.db_log_handler import DbLogHandler
from shared.kernel.settings.settings import ApplicationSettings


def _record() -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)


def test_write_failure_does_not_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Main processing never fails because of logging."""
    handler = DbLogHandler()
    monkeypatch.setattr(handler, "handleError", _ignore)
    monkeypatch.setattr(
        "shared.kernel.logging.db_log_handler.write_log_rows",
        _raise,
    )

    handler.emit(_record())  # no exception escapes


def test_write_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failures are reported via ``handleError`` (stderr), not silently dropped."""
    handler = DbLogHandler()
    reported: list[logging.LogRecord] = []
    monkeypatch.setattr(handler, "handleError", reported.append)
    monkeypatch.setattr(
        "shared.kernel.logging.db_log_handler.write_log_rows",
        _raise,
    )

    record = _record()
    handler.emit(record)

    assert reported == [record]


def _raise(rows: object) -> None:
    raise RuntimeError("database is locked")


def _ignore(record: logging.LogRecord) -> None:
    """Replaces ``handleError`` (keeps stderr clean during tests)."""


def test_unreadable_system_settings_are_reported_once(caplog: pytest.LogCaptureFixture) -> None:
    """Being unable to read settings from the DB is warned only once (warning on every TTL would flood)."""
    settings = ApplicationSettings(env={})

    with caplog.at_level(logging.DEBUG, logger="shared.kernel.settings.settings"):
        # No engine configured = unreadable. Defeat the TTL and read twice
        assert settings.log_level == "INFO"
        settings.reload_db_overrides()
        assert settings.log_level == "INFO"

    messages = [record.message for record in caplog.records]
    assert messages.count("system_settings_unreadable") == 1
