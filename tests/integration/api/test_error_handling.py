"""失敗したときに、応答とログの両方へ必要なものが残ること。

ルーターを抜けた例外は例外ハンドラが応答へ変える。そこで記録しないと、アプリ
ログにはアクセスログの 1 行（ステータスコードだけ）しか残らず、「何が起きたか」
——エラーコード・入力検証で落ちた項目・traceback——が失われる
（:mod:`presentation.fastapi.error_handling`）。

想定外の例外については応答も見る。受け皿が無いと Starlette は text/plain の
``Internal Server Error`` を返す。API クライアントは本文を JSON として読むので、
その場合コードを取り出せず ``unknown_error`` としか表示できない。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bounded_contexts.account_security.domain.exceptions import TotpNotEnrolledError
from presentation.fastapi.error_handling import INTERNAL_ERROR_CODE

_ALLOWED_ORIGIN = "https://app.example.com"
_ERROR_LOGGER = "presentation.fastapi.error_handling"


def _add_failing_endpoints(app: FastAPI) -> None:
    @app.get("/api/test/boom")
    async def _boom() -> None:
        raise RuntimeError("boom")

    @app.get("/api/test/domain-error")
    async def _domain_error() -> None:
        raise TotpNotEnrolledError


@pytest.fixture
def client_with_failing_endpoint(app: FastAPI) -> TestClient:
    _add_failing_endpoints(app)
    # 例外を送出させずに応答を確かめる（本番の ASGI サーバーと同じ扱い）。
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cors_client_with_failing_endpoint(
    engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """別オリジンのフロントエンドを許可した構成でアプリを組み立てる。"""
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
    """ログの該当行を引けるよう、応答にも requestId を載せる。"""
    response = client_with_failing_endpoint.get("/api/test/boom")

    assert response.headers.get("X-Request-Id")


def test_cross_origin_client_can_read_the_error_code(cors_client_with_failing_endpoint: TestClient) -> None:
    """別オリジンからでも本文を読めるよう、500 応答にも CORS ヘッダーを付ける。

    ``Exception`` ハンドラは CORS ミドルウェアの外側に載るため、そこだけに頼ると
    ``Access-Control-Allow-Origin`` が付かない。ブラウザは本文を捨て、画面は
    ``unknown_error`` へ戻ってしまう（受け皿を足した意味が無くなる）。
    """
    response = cors_client_with_failing_endpoint.get("/api/test/boom", headers={"Origin": _ALLOWED_ORIGIN})

    assert response.status_code == 500
    assert response.json()["detail"]["error"] == INTERNAL_ERROR_CODE
    assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


def test_failed_request_is_recorded_in_the_access_log(
    client_with_failing_endpoint: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """500 もアクセスログに残す。例外が記録層を素通りすると 500 だけ抜け落ちる。"""
    with caplog.at_level(logging.INFO, logger="app.request"):
        client_with_failing_endpoint.get("/api/test/boom")

    statuses = [getattr(record, "status_code", None) for record in caplog.records if record.name == "app.request"]
    assert 500 in statuses


def test_unhandled_exception_is_logged_with_a_traceback(
    client_with_failing_endpoint: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """原因を追えるのは traceback だけ。``log`` テーブルの ``trace`` 列へ入る。"""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        client_with_failing_endpoint.get("/api/test/boom")

    records = _records(caplog)
    assert [record.levelno for record in records] == [logging.ERROR]
    assert records[0].message == "unhandled_exception"
    assert records[0].exc_info is not None


def test_client_error_is_logged_with_its_error_code(
    client: TestClient, admin_headers: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    """404 のような ``HTTPException`` も「何が起きたか」を残す。"""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        assert client.delete("/api/admin/users/999999", headers=admin_headers).status_code == 404

    records = _records(caplog)
    assert [record.levelno for record in records] == [logging.WARNING]
    assert records[0].error_code == "user_not_found"  # type: ignore[attr-defined]
    assert records[0].status_code == 404  # type: ignore[attr-defined]


def test_domain_error_is_logged(client_with_failing_endpoint: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    """ドメイン例外のハンドラも同じ受け皿で記録する（レベルと項目が揃う）。"""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        assert client_with_failing_endpoint.get("/api/test/domain-error").status_code == 409

    records = _records(caplog)
    assert [record.error_code for record in records] == ["totp_not_enrolled"]  # type: ignore[attr-defined]


def test_validation_failure_logs_the_fields_but_not_the_values(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """項目名と理由だけを残す。入力値を残すと PII がログへ移る（CLAUDE.md「ログ」）。"""
    with caplog.at_level(logging.DEBUG, logger=_ERROR_LOGGER):
        response = client.post("/api/auth/login", json={"email": "leaked@example.com"})

    assert response.status_code == 422
    records = _records(caplog)
    assert [record.levelno for record in records] == [logging.WARNING]
    assert "body.password:missing" in records[0].invalid_fields  # type: ignore[attr-defined]
    assert "leaked@example.com" not in records[0].invalid_fields  # type: ignore[attr-defined]
