"""On failure, what is needed remains in both the response and the logs.

Exceptions leaving a router are turned into responses by the exception handlers. Without
recording there, the app log keeps only the access-log line (status code only), and "what
happened" (the error code, the fields that failed validation, the traceback) is lost
(:mod:`presentation.fastapi.error_handling`).

For unexpected exceptions the response is checked too. Without a catch-all, Starlette returns
text/plain ``Internal Server Error``. The API client reads the body as JSON, so it cannot extract a
code and can only show ``unknown_error``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Annotated

import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.account_security.domain.exceptions import TotpNotEnrolledError
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.error_handling import INTERNAL_ERROR_CODE
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.domain.auth import master_data
from tests.conftest import sign_in

_ALLOWED_ORIGIN = "https://app.example.com"
_ERROR_LOGGER = "presentation.fastapi.error_handling"


def _add_failing_endpoints(app: FastAPI) -> None:
    @app.get("/api/test/boom")
    async def _boom() -> None:
        raise RuntimeError("boom")

    @app.get("/api/test/domain-error")
    async def _domain_error() -> None:
        raise TotpNotEnrolledError

    @app.get("/api/test/authenticated-boom")
    async def _authenticated_boom(
        _principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    ) -> None:
        raise RuntimeError("boom")


@pytest.fixture
def client_with_failing_endpoint(app: FastAPI) -> TestClient:
    _add_failing_endpoints(app)
    # Check the response without raising the exception (same as the production ASGI server).
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cors_client_with_failing_endpoint(
    engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """Builds the app configured to allow a cross-origin frontend."""
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", f'["{_ALLOWED_ORIGIN}"]')
    app = create_app()
    _add_failing_endpoints(app)
    yield TestClient(app, raise_server_exceptions=False)


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _ERROR_LOGGER]


def test_unhandled_exception_returns_a_json_error_code(client_with_failing_endpoint: TestClient) -> None:
    response = client_with_failing_endpoint.get("/api/test/boom")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"]["error"] == INTERNAL_ERROR_CODE


def test_unhandled_exception_does_not_leak_the_exception_text(client_with_failing_endpoint: TestClient) -> None:
    response = client_with_failing_endpoint.get("/api/test/boom")

    assert "boom" not in response.text
    assert "RuntimeError" not in response.text


def test_unhandled_exception_carries_the_request_id(client_with_failing_endpoint: TestClient) -> None:
    """The response carries the requestId too, so the matching log line can be looked up."""
    response = client_with_failing_endpoint.get("/api/test/boom")

    assert response.headers.get("X-Request-Id")


def test_cross_origin_client_can_read_the_error_code(cors_client_with_failing_endpoint: TestClient) -> None:
    """500 responses also carry CORS headers so the body can be read cross-origin.

    The ``Exception`` handler sits outside the CORS middleware, so relying on it alone leaves out
    ``Access-Control-Allow-Origin``. The browser discards the body and the screen falls back to
    ``unknown_error`` (defeating the point of the catch-all).
    """
    response = cors_client_with_failing_endpoint.get("/api/test/boom", headers={"Origin": _ALLOWED_ORIGIN})

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == INTERNAL_ERROR_CODE
    assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


def test_failed_request_is_recorded_in_the_access_log(
    client_with_failing_endpoint: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """500s are access-logged too. If the exception bypassed the logging layer, only the 500s would be missing."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        client_with_failing_endpoint.get("/api/test/boom")

    statuses = [getattr(record, "status_code", None) for record in caplog.records if record.name == "app.request"]
    assert 500 in statuses


def test_unhandled_exception_is_logged_with_a_traceback(
    client_with_failing_endpoint: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only the traceback lets you trace the cause. It goes into the ``trace`` column of the ``log`` table."""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        client_with_failing_endpoint.get("/api/test/boom")

    records = _records(caplog)
    assert [record.levelno for record in records] == [logging.ERROR]
    assert records[0].message == "unhandled_exception"
    assert records[0].exc_info is not None


def test_client_error_is_logged_with_its_error_code(
    client: TestClient, admin_headers: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    """``HTTPException`` such as 404 also records "what happened"."""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        assert client.delete("/api/admin/users/999999", headers=admin_headers).status_code == 404

    records = _records(caplog)
    assert [record.levelno for record in records] == [logging.WARNING]
    assert records[0].error_code == "user_not_found"  # type: ignore[attr-defined]
    assert records[0].status_code == 404  # type: ignore[attr-defined]


def test_domain_error_is_logged(client_with_failing_endpoint: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """The domain exception handler records through the same catch-all (same level and fields)."""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        assert client_with_failing_endpoint.get("/api/test/domain-error").status_code == 409

    records = _records(caplog)
    assert [record.error_code for record in records] == ["totp_not_enrolled"]  # type: ignore[attr-defined]


def test_validation_failure_logs_the_fields_but_not_the_values(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Only field names and reasons are kept. Keeping input values would move PII into logs (CLAUDE.md "Logging")."""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        response = client.post("/api/auth/login", json={"email": "leaked@example.com"})

    assert response.status_code == 422
    records = _records(caplog)
    assert [record.levelno for record in records] == [logging.WARNING]
    assert "body.password:missing" in records[0].invalid_fields  # type: ignore[attr-defined]
    assert "leaked@example.com" not in records[0].invalid_fields  # type: ignore[attr-defined]


def test_the_500_log_line_knows_whose_request_it_was(
    client_with_failing_endpoint: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """When an authenticated request fails, the log line carries ``user_id_hash``.

    If ``InternalErrorMiddleware`` were a ``BaseHTTPMiddleware``, downstream would run in **a separate
    task**, so ``contextvars`` set by the auth dependency would not propagate and only the 500 line
    would lack "whose request it was". That is why it is written as plain ASGI.
    """
    # The session is held in a cookie, so sign in **with this client** (ADR-0076 §4).
    sign_in(client_with_failing_endpoint, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        response = client_with_failing_endpoint.get("/api/test/authenticated-boom")

    assert response.status_code == 500
    records = _records(caplog)
    assert [record.user_id_hash for record in records] != [None]  # type: ignore[attr-defined]


def _access_log_lines(caplog: pytest.LogCaptureFixture, path: str) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == "app.request" and record.path == path  # type: ignore[attr-defined]
    ]


def test_the_access_log_line_knows_whose_request_it_was(
    client_with_failing_endpoint: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """For an authenticated request, the ``http_request`` line carries ``user_id_hash``.

    If ``RequestLoggingMiddleware`` were a ``BaseHTTPMiddleware``, it would be empty for the same reason
    as the 500 line. Also checks that the line has the same user and that the value does not carry
    over to the next unauthenticated request.
    """
    sign_in(client_with_failing_endpoint, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    with caplog.at_level(logging.DEBUG):
        response = client_with_failing_endpoint.get("/api/test/authenticated-boom")
        client_with_failing_endpoint.cookies.clear()
        client_with_failing_endpoint.get("/api/test/authenticated-boom")
        client_with_failing_endpoint.get("/api/test/boom")

    signed_in, signed_out = _access_log_lines(caplog, "/api/test/authenticated-boom")
    assert response.status_code == 500
    assert signed_in.status_code == 500  # type: ignore[attr-defined]
    assert signed_in.user_id_hash is not None  # type: ignore[attr-defined]
    assert signed_in.request_id == response.headers["X-Request-Id"]  # type: ignore[attr-defined]
    assert signed_out.status_code == 401  # type: ignore[attr-defined]
    assert signed_out.user_id_hash is None  # type: ignore[attr-defined]
    assert [line.user_id_hash for line in _access_log_lines(caplog, "/api/test/boom")] == [None]  # type: ignore[attr-defined]
