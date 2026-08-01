"""アクセスログ（``app.request``）に何を残し、何を残さないか。

見たいのは 2 つ。

- **死活監視のパスは残さない。** Docker の healthcheck は数十秒おきに叩くため、
  成功した分まで残すとアプリログがこれで埋まる。
- **失敗はレベルで拾える。** 4xx は WARNING、5xx は ERROR。成功と同じ INFO で
  並べると、ログを絞り込んでも異常が浮かび上がらない。
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
    """プローブが落ちていること自体は知りたい情報なので、失敗は残す。"""
    with caplog.at_level(logging.DEBUG, logger=_ACCESS_LOGGER):
        # HEAD は定義していない = 405。プローブのパスでも失敗なら記録される
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
        # 401 は運用上ふつうに起きる（期限切れ・未ログイン）ので INFO のまま
        logging.INFO,
        logging.WARNING,
    ]
