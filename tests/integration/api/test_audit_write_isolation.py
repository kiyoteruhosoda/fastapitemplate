"""DB writes of logs and audit records do not collide with the request transaction.

Uses **file-backed SQLite**. The shared fixture's in-memory + ``StaticPool`` has everyone share one
connection, so no lock contention occurs and this bug cannot be reproduced (it does occur with the
production default ``sqlite:///app.db``).

Shape of the bug (ADR-0075 §1): writing from another connection mid-processing collides with the
write lock held by a request that has done ``db.flush()``, waits out the busy timeout (5 s) and
fails with ``database is locked``. The writer swallows the exception, so **the operation succeeds
but the record is lost**. Audit logs (``audit_log``) and app logs (``log``) use the same path, so
both are checked here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import bounded_contexts.account_security.infrastructure.account_security_models
import bounded_contexts.audit.infrastructure.audit_log_model
import bounded_contexts.example.infrastructure.item_model  # noqa: F401 — metadata registration
import shared.infrastructure.models  # noqa: F401 — metadata registration
from shared.domain.auth import master_data
from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data
from shared.infrastructure.tenant_directory import seat_default_admin
from shared.kernel.database import db as db_module
from shared.kernel.database.db import Base
from shared.kernel.settings.settings import settings
from tests.conftest import sign_in

# A blocked write from another connection waits until the busy timeout (5 s by default).
# If a request takes longer than this, it is waiting on a lock.
_SLOW_REQUEST_SECONDS = 3.0


@pytest.fixture
def file_engine(tmp_path: Path) -> Iterator[sa.Engine]:
    """File-backed SQLite that does not share connections."""
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)
    db_module.set_engine(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_master_data(session)
    ensure_default_admin(session)
    seat_default_admin(session, issuer="", client_id="")
    session.commit()
    session.close()
    yield engine
    db_module.set_engine(None)
    settings.reload_db_overrides()
    engine.dispose()


@pytest.fixture
def file_client(file_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """An app with DB log writes enabled.

    The shared test environment disables writes to the ``log`` table with ``TESTING=1`` (so log rows
    do not pile up with every test). This module checks **that write path itself**, so it is enabled
    here only.

    ``setup_logging`` replaces the root logger, so it is restored on teardown. Otherwise later tests
    keep a handler that writes to a disposed engine.

    **The test client's own httpx2 logs ("HTTP Request: …") are not sent to the DB.** Since Starlette
    1.10, TestClient returns once the response head arrives while the app keeps running in the
    background. httpx2 emits its line at that point, so it becomes a direct write from outside the
    request (a context without the queue), collides with the app still holding the write lock, and
    waits 5 seconds. It is a client-side line that does not exist in production, and we want to see
    the app's lines, so only this logger is silenced.
    """
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("TESTING", "0")
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    client_logger = logging.getLogger("httpx2")
    original_client_level = client_logger.level
    client_logger.setLevel(logging.WARNING)
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        root.handlers = original_handlers
        client_logger.setLevel(original_client_level)


@pytest.fixture
def file_admin_headers(file_client: TestClient) -> dict[str, str]:
    return sign_in(file_client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)


def _audit_rows(engine: sa.Engine, event_type: str) -> list[sa.Row[str, str]]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                sa.text("SELECT target_id, result FROM audit_log WHERE event_type = :t"),
                {"t": event_type},
            )
        )


def test_a_write_endpoint_records_its_audit_event(
    file_client: TestClient, file_admin_headers: dict[str, str], file_engine: sa.Engine
) -> None:
    """Even operations that go through ``db.flush()`` leave an audit record without slowing down on lock waits."""
    started = time.perf_counter()
    response = file_client.post(
        "/api/admin/users",
        json={"email": "locked@example.com", "username": "locked", "password": "password123", "roles": []},
        headers=file_admin_headers,
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 201, response.text
    assert elapsed < _SLOW_REQUEST_SECONDS, f"Audit write is waiting on a lock ({elapsed:.1f} s)"
    assert _audit_rows(file_engine, "user.created") == [(str(response.json()["id"]), "success")]


def test_a_rolled_back_request_still_records_its_audit_event(file_client: TestClient, file_engine: sa.Engine) -> None:
    """A failed sign-in is recorded even when the request is rolled back with 401."""
    response = file_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert _audit_rows(file_engine, "login.failed") == [(str(master_data.DEFAULT_ADMIN_ID), "failure")]


def test_a_log_line_emitted_after_a_write_is_stored(file_client: TestClient, file_engine: sa.Engine) -> None:
    """Log lines emitted after a write also reach ``log`` without slowing down on lock waits.

    ``forgot-password`` emits a warning (``password_reset_mail_disabled``) after ``flush()``ing the
    token. An implementation that writes to the DB mid-processing would wait 5 seconds for this one
    line and then lose it.
    """
    started = time.perf_counter()
    response = file_client.post("/api/auth/forgot-password", json={"email": master_data.DEFAULT_ADMIN_EMAIL})
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < _SLOW_REQUEST_SECONDS, f"Log write is waiting on a lock ({elapsed:.1f} s)"
    with file_engine.connect() as connection:
        stored = list(
            connection.execute(sa.text("SELECT message FROM log WHERE message = 'password_reset_mail_disabled'"))
        )
    assert len(stored) == 1


def test_the_access_log_line_is_stored(file_client: TestClient, file_engine: sa.Engine) -> None:
    """Access logs (one line per request) are recorded too.

    Health-check paths (``/healthz`` etc.) are not access-logged, so a normal API is called here
    (:mod:`presentation.fastapi.middleware.request_logging`).
    """
    assert file_client.get("/info").status_code == 200

    with file_engine.connect() as connection:
        stored = list(connection.execute(sa.text("SELECT path, status_code FROM log WHERE logger = 'app.request'")))
    assert ("/info", 200) in [(row[0], row[1]) for row in stored]


def test_multiple_events_in_one_request_are_all_recorded(
    file_client: TestClient, file_admin_headers: dict[str, str], file_engine: sa.Engine
) -> None:
    """Queues do not mix across multiple requests, and every entry is written."""
    for index in range(3):
        created = file_client.post(
            "/api/admin/users",
            json={
                "email": f"batch{index}@example.com",
                "username": f"batch{index}",
                "password": "password123",
                "roles": [],
            },
            headers=file_admin_headers,
        )
        assert created.status_code == 201, created.text

    assert len(_audit_rows(file_engine, "user.created")) == 3


def test_the_error_code_reaches_the_log_table(file_client: TestClient, file_engine: sa.Engine) -> None:
    """Failure records reach the DB together with "what happened".

    Only fields that have columns go into the ``log`` table; the rest of ``extra`` appears only in the
    stdout JSON. That is why the error code is also put in the message: if it cannot be read from the
    admin screen (`/admin/logs`), recording it is pointless.
    """
    assert file_client.get("/api/admin/users", headers={"Authorization": "Bearer nope"}).status_code == 401

    with file_engine.connect() as connection:
        stored = list(
            connection.execute(sa.text("SELECT message, status_code FROM log WHERE message LIKE 'request_failed%'"))
        )
    assert ("request_failed: invalid_token", 401) in [(row[0], row[1]) for row in stored]
