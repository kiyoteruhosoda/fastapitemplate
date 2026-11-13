"""Shared test fixtures (SQLite in-memory with master data seeded)."""

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
from bounded_contexts.content_settings.infrastructure import content_setting_model
from bounded_contexts.example.infrastructure import item_model
from bounded_contexts.identity_federation.infrastructure import identity_federation_models
from bounded_contexts.notes.infrastructure import note_model
from bounded_contexts.notification.infrastructure import notification_models
from presentation.fastapi.middleware.csrf import CSRF_COOKIE, CSRF_HEADER
from shared.domain.auth import master_data
from shared.infrastructure import models as shared_models
from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data
from shared.infrastructure.models import Tenant
from shared.infrastructure.system_administrators import create_system_administrator
from shared.infrastructure.tenant_directory import DEFAULT_TENANT_SLUG, seat_default_admin
from shared.kernel.database import db as db_module
from shared.kernel.database.db import Base
from shared.kernel.settings.settings import settings

# ⚠ **Merely importing gets removed by ``ruff --fix``.** Models register with ``Base.metadata`` as
# an import side effect, so they look like "unused imports" and are stripped one line at a time as
# F401. Once gone, tests fail with "table does not exist", **in a way that does not point to the
# import**. Referencing them makes them impossible to remove (``migrations/env.py`` does the same).
_REGISTERED_MODELS = (
    account_security_models,
    audit_log_model,
    content_setting_model,
    item_model,
    identity_federation_models,
    note_model,
    notification_models,
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
    # ⚠ **Read settings before opening the session.** The settings reader queries the DB on a
    # separate connection, but with ``StaticPool`` it is the same connection, so closing it rolls back
    # the half-seeded session.
    issuer, client_id = settings.oidc_issuer, settings.oidc_client_id
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_master_data(session)
    ensure_default_admin(session)
    seat_default_admin(session, issuer=issuer, client_id=client_id)
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
    """Another browser (a separate session).

    Now that tokens travel in cookies, **one ``TestClient`` can hold only one session** (just like a
    browser). Tests that switch between the administrator and a regular user use one client per identity.
    """
    with TestClient(app) as c:
        yield c


def register_issuer(issuer: str, client_id: str = "rp") -> None:
    """Registers the default tenant as this issuer's assay tenant (ADR-0079 §1).

    Tokens from unregistered issuers are rejected. SSO tests replace ``OIDC_ISSUER`` after the
    fixture, so it is copied to the default tenant at that point.
    """
    with sessionmaker(bind=db_module.get_engine())() as session:
        tenant = session.scalar(sa.select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG))
        assert tenant is not None
        tenant.issuer = issuer
        tenant.client_id = client_id
        session.commit()


def sign_in(client: TestClient, email: str, password: str, tenant: str | None = None) -> dict[str, str]:
    """Signs in and returns the headers needed for writes (ADR-0076 §4).

    The token travels in a cookie and ``TestClient`` keeps it, so only the CSRF double-submit token is
    returned. **Read it again every time the session is re-established**: the CSRF token is renewed
    with each new session.
    """
    # ``tenant`` is the entrance tenant (``/t/<slug>/login``; ADR-0079 §4). Needed when there are two or more tenants
    response = client.post("/api/auth/login", json={"email": email, "password": password, "tenant": tenant})
    assert response.status_code == 200, response.text
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    """Signs in as the administrator and returns the headers needed for writes (ADR-0076 §4).

    The token is not in the response body but travels in a cookie. ``TestClient`` keeps cookies, so
    **returning only the CSRF double-submit token** is enough.
    """
    return sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)


SYSTEM_ADMIN_EMAIL = "system-admin@example.com"
SYSTEM_ADMIN_PASSWORD = "system-admin-password-1"


@pytest.fixture
def system_admin_headers(client: TestClient, engine: sa.Engine) -> dict[str, str]:
    """Signs in as the system administrator (a user belonging to no tenant; ADR-0079 §1).

    System-wide records (such as sign-in failures with an unknown target) are not visible to tenant administrators.
    """
    # Created the same way as the first one in production (``scripts/create_system_admin.py``)
    with sessionmaker(bind=engine)() as session:
        created = create_system_administrator(
            session, email=SYSTEM_ADMIN_EMAIL, username="system-admin", password=SYSTEM_ADMIN_PASSWORD
        )
        assert created
        session.commit()
    return sign_in(client, SYSTEM_ADMIN_EMAIL, SYSTEM_ADMIN_PASSWORD)
