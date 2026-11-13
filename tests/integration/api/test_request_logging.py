"""What the access log (``app.request``) records and what it does not.

Two things are checked.

- **Health-check paths are not recorded.** Docker's healthcheck calls them every few tens of
    seconds, so recording successful ones too would flood the app log.
- **Failures can be picked out by level.** 4xx is WARNING, 5xx is ERROR. Listed at the same INFO
    as successes, anomalies would not stand out even when filtering logs.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

_ACCESS_LOGGER = "app.request"


def _access_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _ACCESS_LOGGER]


@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/api/health", "/metrics"])
def test_successful_probes_are_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture, path: str) -> None:
    with caplog.at_level(logging.DEBUG, logger=_ACCESS_LOGGER):
        assert client.get(path).status_code == 200

    assert _access_records(caplog) == []


def test_a_failing_probe_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """A failing probe is itself useful information, so failures are recorded."""
    with caplog.at_level(logging.DEBUG, logger=_ACCESS_LOGGER):
        # HEAD is not defined = 405. Failures are recorded even on probe paths
        assert client.head("/healthz").status_code == 405

    assert [record.levelno for record in _access_records(caplog)] == [logging.WARNING]


def test_ordinary_requests_are_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=_ACCESS_LOGGER):
        assert client.get("/info").status_code == 200

    records = _access_records(caplog)
    assert [record.levelno for record in records] == [logging.INFO]
    assert records[0].path == "/info"  # type: ignore[attr-defined]


def test_client_errors_are_logged_as_warnings(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=_ACCESS_LOGGER):
        assert client.get("/api/admin/users", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert client.get("/api/nonexistent").status_code == 404

    assert [record.levelno for record in _access_records(caplog)] == [
        # 401 happens routinely (expired, not signed in), so it stays INFO
        logging.INFO,
        logging.WARNING,
    ]
