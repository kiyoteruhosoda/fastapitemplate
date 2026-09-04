"""テスト共通フィクスチャ（SQLite in-memory + マスタデータ投入済み）。"""

from __future__ import annotations

import os

os.environ.setdefault("TESTING", "1")

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bounded_contexts.account_security.infrastructure import account_security_models
from bounded_contexts.audit.infrastructure import audit_log_model
from bounded_contexts.example.infrastructure import item_model
from bounded_contexts.identity_federation.infrastructure import identity_federation_models
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from shared.domain.auth import master_data
from shared.infrastructure import models as shared_models
from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data
from shared.kernel.database import db as db_module
from shared.kernel.database.db import Base
from shared.kernel.settings.settings import settings

# ⚠ **import しただけでは ``ruff --fix`` に消される。** モデルは import の副作用で
# ``Base.metadata`` へ登録されるので「使っていない import」に見え、F401 として 1 行ずつ
# 剥がされる。消えると「テーブルが無い」で落ちるが、**落ち方が import と結び付かない**。
# 参照して使うことで、消せない形にしてある（``migrations/env.py`` も同じ）。
_REGISTERED_MODELS = (
    account_security_models,
    audit_log_model,
    item_model,
    identity_federation_models,
    shared_models,
)


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
def db_session(engine: sa.Engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def app(engine: sa.Engine) -> FastAPI:
    from presentation.fastapi.app import create_app

    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_client(app: FastAPI) -> Iterator[TestClient]:
    """もう 1 つのブラウザ（別のセッション）。

    トークンを Cookie で運ぶようになったので、**1 つの ``TestClient`` が持てる
    セッションは 1 つ**になった（ブラウザと同じ）。管理者と一般利用者を行き来する
    テストは、identity ごとにクライアントを分ける。
    """
    with TestClient(app) as c:
        yield c


def sign_in(client: TestClient, email: str, password: str) -> dict[str, str]:
    """ログインして、更新系に必要なヘッダーを返す（ADR-0028）。

    トークンは Cookie で運ばれ ``TestClient`` が保持するので、返すのは CSRF の
    二重送信トークンだけ。**セッションを張り直すたびに読み直す** ——CSRF トークンは
    セッションを作るたびに新しくなる。
    """
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    """管理者としてログインし、更新系に必要なヘッダーを返す（ADR-0028）。

    トークンは応答本文に載らず Cookie で運ばれる。``TestClient`` が Cookie を
    保持するので、**返すのは CSRF の二重送信トークンだけ**でよい。
    """
    return sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
