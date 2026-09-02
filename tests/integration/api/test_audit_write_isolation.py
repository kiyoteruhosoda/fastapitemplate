"""ログ・監査の DB 書き込みが、リクエストのトランザクションと衝突しないこと。

**ファイル実体の SQLite** を使う。共通フィクスチャの in-memory + ``StaticPool`` は
全員が 1 本のコネクションを共有するため、ロックの競合が起きず、この不具合を
再現できない（実運用の既定 ``sqlite:///app.db`` では起きる）。

不具合の形（ADR-0013）: 処理の途中で別コネクションから書くと、``db.flush()`` 済みの
リクエストが握った書き込みロックと衝突し、busy timeout（5 秒）待った末に
``database is locked`` で落ちる。書き込み側は例外を握りつぶすので、**操作は成功した
のに記録だけ残らない**状態になる。監査ログ（``audit_log``）とアプリログ（``log``）の
どちらも同じ経路なので、両方をここで見る。
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
import bounded_contexts.example.infrastructure.item_model  # noqa: F401 — メタデータ登録
import shared.infrastructure.models  # noqa: F401 — メタデータ登録
from shared.domain.auth import master_data
from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data
from shared.kernel.database import db as db_module
from shared.kernel.database.db import Base
from shared.kernel.settings.settings import settings

# 別コネクションからの書き込みが詰まると busy timeout（既定 5 秒）まで待つ。
# 1 リクエストがこれを超えるようなら、ロックで待たされている。
_SLOW_REQUEST_SECONDS = 3.0


@pytest.fixture
def file_engine(tmp_path: Path) -> Iterator[sa.Engine]:
    """コネクションを共有しない、ファイル実体の SQLite。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)
    db_module.set_engine(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_master_data(session)
    ensure_default_admin(session)
    session.commit()
    session.close()
    yield engine
    db_module.set_engine(None)
    settings.reload_db_overrides()
    engine.dispose()


@pytest.fixture
def file_client(file_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """DB へのログ書き込みを有効にしたアプリ。

    共通のテスト環境は ``TESTING=1`` で ``log`` テーブルへの書き込みを切っている
    （テストのたびにログ行が増えないようにするため）。ここは**その書き込み経路
    そのもの**を見るので、このモジュールでだけ有効にする。

    ``setup_logging`` はルートロガーを差し替えるので、後始末で元へ戻す。戻さないと
    後続のテストが、破棄済みのエンジンへ書きに行くハンドラを抱えたままになる。
    """
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("TESTING", "0")
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        root.handlers = original_handlers


@pytest.fixture
def file_admin_headers(file_client: TestClient) -> dict[str, str]:
    response = file_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _audit_rows(engine: sa.Engine, event_type: str) -> list[sa.Row[tuple[str, str]]]:
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
    """``db.flush()`` を通る操作でも監査ログが残り、ロック待ちで遅くならないこと。"""
    started = time.perf_counter()
    response = file_client.post(
        "/api/admin/users",
        json={"email": "locked@example.com", "username": "locked", "password": "password123", "roles": []},
        headers=file_admin_headers,
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 201, response.text
    assert elapsed < _SLOW_REQUEST_SECONDS, f"監査の書き込みがロックを待っている（{elapsed:.1f} 秒）"
    assert _audit_rows(file_engine, "user.created") == [(str(response.json()["id"]), "success")]


def test_a_rolled_back_request_still_records_its_audit_event(file_client: TestClient, file_engine: sa.Engine) -> None:
    """401 でリクエストがロールバックされても、ログイン失敗は残ること。"""
    response = file_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert _audit_rows(file_engine, "login.failed") == [(str(master_data.DEFAULT_ADMIN_ID), "failure")]


def test_a_log_line_emitted_after_a_write_is_stored(file_client: TestClient, file_engine: sa.Engine) -> None:
    """書き込みの後に出たログ行も ``log`` に残り、ロック待ちで遅くならないこと。

    ``forgot-password`` はトークンを ``flush()`` した後に警告
    （``password_reset_mail_disabled``）を出す。処理の途中で DB へ書く実装だと、
    この 1 行のために 5 秒待った末に行が消える。
    """
    started = time.perf_counter()
    response = file_client.post("/api/auth/forgot-password", json={"email": master_data.DEFAULT_ADMIN_EMAIL})
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < _SLOW_REQUEST_SECONDS, f"ログの書き込みがロックを待っている（{elapsed:.1f} 秒）"
    with file_engine.connect() as connection:
        stored = list(
            connection.execute(sa.text("SELECT message FROM log WHERE message = 'password_reset_mail_disabled'"))
        )
    assert len(stored) == 1


def test_the_access_log_line_is_stored(file_client: TestClient, file_engine: sa.Engine) -> None:
    """アクセスログ（リクエストごとの 1 行）も残ること。

    死活監視のパス（``/healthz`` 等）はアクセスログに残さないので、ここでは
    通常の API を叩く（:mod:`presentation.fastapi.middleware.request_logging`）。
    """
    assert file_client.get("/info").status_code == 200

    with file_engine.connect() as connection:
        stored = list(connection.execute(sa.text("SELECT path, status_code FROM log WHERE logger = 'app.request'")))
    assert ("/info", 200) in [(row[0], row[1]) for row in stored]


def test_multiple_events_in_one_request_are_all_recorded(
    file_client: TestClient, file_admin_headers: dict[str, str], file_engine: sa.Engine
) -> None:
    """複数リクエストにまたがっても控えが混ざらず、全件書かれること。"""
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
    """失敗の記録が「何が起きたか」ごと DB に残ること。

    ``log`` テーブルへ入るのは列にある項目だけで、``extra`` の残りは stdout の
    JSON にしか出ない。エラーコードを本文にも入れているのはこのため——管理画面
    （`/admin/logs`）から読めなければ、記録した意味がない。
    """
    assert file_client.get("/api/admin/users", headers={"Authorization": "Bearer nope"}).status_code == 401

    with file_engine.connect() as connection:
        stored = list(
            connection.execute(sa.text("SELECT message, status_code FROM log WHERE message LIKE 'request_failed%'"))
        )
    assert ("request_failed: invalid_token", 401) in [(row[0], row[1]) for row in stored]
