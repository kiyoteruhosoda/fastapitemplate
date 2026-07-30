"""アプリログ閲覧 API（``GET /api/admin/logs``）の絞り込みとページング。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from shared.infrastructure.models import Log
from shared.infrastructure.models.base import utcnow


def _insert_log(engine: sa.Engine, **overrides: object) -> None:
    session = sessionmaker(bind=engine)()
    defaults = {
        "created_at": utcnow(),
        "level": "INFO",
        "logger": "test",
        "message": "hello",
        "request_id": "req-1",
    }
    session.add(Log(**{**defaults, **overrides}))
    session.commit()
    session.close()


def _search(client: TestClient, headers: dict[str, str], query: str = "") -> dict[str, Any]:
    response = client.get(f"/api/admin/logs{query}", headers=headers)
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()
    return payload


def _messages(payload: dict[str, Any]) -> list[str]:
    return [entry["message"] for entry in payload["entries"]]


def test_logs_require_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/logs").status_code == 401


def test_list_logs_returns_total_and_entries(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    _insert_log(engine, level="INFO", request_id="req-1")
    _insert_log(engine, level="ERROR", request_id="req-2", message="boom")

    payload = _search(client, admin_headers)
    assert payload["total"] >= 2
    assert len(payload["entries"]) == payload["total"]


def test_filters_by_level_case_insensitively(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    _insert_log(engine, level="INFO")
    _insert_log(engine, level="ERROR", message="boom")

    assert _messages(_search(client, admin_headers, "?level=error")) == ["boom"]
    assert _messages(_search(client, admin_headers, "?level=ERROR")) == ["boom"]


def test_filters_by_request_id(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    _insert_log(engine, request_id="req-1")
    _insert_log(engine, request_id="req-2", message="boom")

    payload = _search(client, admin_headers, "?request_id=req-2")
    assert _messages(payload) == ["boom"]


def test_filters_by_logger_prefix_and_message_substring(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    _insert_log(engine, logger="app.request", message="http_request")
    _insert_log(engine, logger="bounded_contexts.example", message="item_created")

    assert _messages(_search(client, admin_headers, "?logger=app.")) == ["http_request"]
    assert _messages(_search(client, admin_headers, "?message=item_")) == ["item_created"]


def test_wildcards_in_the_filter_are_literal_text(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """``%`` を渡しても全件一致にならない（LIKE パターンとして解釈しない）。"""
    _insert_log(engine, message="plain")
    _insert_log(engine, message="100% done")

    assert _messages(_search(client, admin_headers, "?message=%25")) == ["100% done"]


def test_filters_by_period(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    now = utcnow()
    _insert_log(engine, created_at=now - timedelta(days=2), message="old")
    _insert_log(engine, created_at=now, message="recent")

    boundary = (now - timedelta(days=1)).isoformat()
    assert _messages(_search(client, admin_headers, f"?created_from={boundary}")) == ["recent"]
    assert _messages(_search(client, admin_headers, f"?created_to={boundary}")) == ["old"]


def test_accepts_offset_aware_period_boundaries(
    client: TestClient, admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """タイムゾーン付きの境界も UTC へ揃えて比較する。"""
    _insert_log(engine, created_at=utcnow() - timedelta(days=2), message="old")
    _insert_log(engine, created_at=utcnow(), message="recent")

    # "+" はクエリ文字列では空白を表すため、オフセットの符号は URL エンコードする
    far_future = (utcnow() + timedelta(days=1)).isoformat() + "%2B09:00"
    assert _messages(_search(client, admin_headers, f"?created_to={far_future}")) == ["recent", "old"]


def test_paginates_newest_first(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    now = utcnow()
    for index in range(3):
        _insert_log(engine, created_at=now + timedelta(seconds=index), message=f"entry-{index}")

    first = _search(client, admin_headers, "?logger=test&limit=2")
    assert _messages(first) == ["entry-2", "entry-1"]
    assert first["total"] == 3

    second = _search(client, admin_headers, "?logger=test&limit=2&offset=2")
    assert _messages(second) == ["entry-0"]
    # total は絞り込み条件に対する件数で、ページの件数ではない
    assert second["total"] == 3


def test_rejects_a_limit_above_the_allowed_maximum(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get("/api/admin/logs?limit=100000", headers=admin_headers).status_code == 422


def test_filter_options_expose_the_selectable_levels(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/logs/filters", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["levels"] == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
