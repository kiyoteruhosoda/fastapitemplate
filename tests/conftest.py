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

import bounded_contexts.account_security.infrastructure.account_security_models
import bounded_contexts.example.infrastructure.item_model  # noqa: F401 — メタデータ登録
import shared.infrastructure.models  # noqa: F401 — メタデータ登録
from shared.infrastructure.master_data_seeder import seed_master_data
from shared.kernel.database import db as db_module
from shared.kernel.database.db import Base
from shared.kernel.settings.settings import settings


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
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
