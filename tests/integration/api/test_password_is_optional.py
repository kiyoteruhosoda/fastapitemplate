"""Whether "has no local authentication" can be expressed in the data (ADR-0076 §6).

A user whose ``users.password_hash`` is NULL cannot sign in with a password, cannot change it, and
**cannot grow one through a reset**. One can only be given when an administrator explicitly sets it.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import PasswordResetToken, User
from shared.infrastructure.tenant_directory import DEFAULT_TENANT_SLUG, tenant_of_slug
from tests.conftest import sign_in

_SSO_ONLY = "sso-only@example.com"


@pytest.fixture
def sso_only_user(db_session: Session) -> User:
    """A user who can only sign in via SSO (has no password)."""
    user = User(email=_SSO_ONLY, username="SSO only", password_hash=None, is_active=True)
    user.join(tenant_of_slug(db_session, DEFAULT_TENANT_SLUG) or 0)
    db_session.add(user)
    db_session.commit()
    return user


def test_an_sso_user_is_provisioned_without_a_password(db_session: Session, engine: sa.Engine) -> None:
    """⚠ Do not fill it with a random value; that would mix "none" with "a value nobody knows"."""
    from bounded_contexts.identity_federation.domain.entities.federated_account import (
        NewFederatedAccount,
    )
    from bounded_contexts.identity_federation.infrastructure.sql_federated_user_directory import (
        SqlFederatedUserDirectory,
    )

    directory = SqlFederatedUserDirectory(db_session, tenant_of_slug(db_session, DEFAULT_TENANT_SLUG))
    created = directory.provision(NewFederatedAccount(email=_SSO_ONLY, username="SSO only", roles=()))
    db_session.commit()

    user = db_session.get(User, created.user_id)
    assert user is not None
    assert user.password_hash is None
    assert user.has_local_password is False


def test_a_user_without_a_password_cannot_sign_in_with_one(client: TestClient, sso_only_user: User) -> None:
    response = client.post("/api/auth/login", json={"email": _SSO_ONLY, "password": "anything-at-all"})
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


def test_a_reset_is_not_issued_for_a_user_without_a_password(
    client: TestClient,
    db_session: Session,
    sso_only_user: User,
) -> None:
    """⚠ Without this, a single reset would grow local authentication."""
    response = client.post("/api/auth/forgot-password", json={"email": _SSO_ONLY})
    # The response is the same as when there is no such recipient (existence is not leaked).
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == sso_only_user.id)) is None


def _take_the_password_away(db_session: Session, email: str) -> None:
    """Takes away only the password of a signed-in user (the session stays).

    The shortest path to the state "a user who can only sign in via SSO is already signed in to this
    app". **Someone with no way in cannot simply be signed in.**
    """
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.password_hash = None
    db_session.commit()


def test_the_screen_is_told_whether_there_is_a_password(client: TestClient, db_session: Session) -> None:
    """The screen uses this to decide whether to offer the password change."""
    sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    assert client.get("/api/auth/me").json()["has_password"] is True

    _take_the_password_away(db_session, master_data.DEFAULT_ADMIN_EMAIL)
    assert client.get("/api/auth/me").json()["has_password"] is False


def test_a_user_without_a_password_cannot_change_one(client: TestClient, db_session: Session) -> None:
    """A user without a password cannot enter a "current password".

    The reason is not distinguished and is unified to ``invalid_current_password`` (so the presence
    of a way in cannot be counted from outside).
    """
    headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    _take_the_password_away(db_session, master_data.DEFAULT_ADMIN_EMAIL)

    response = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "", "new_password": "grown-out-of-nothing-1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_current_password"


def test_an_administrator_can_give_a_password_on_purpose(
    client: TestClient,
    other_client: TestClient,
    sso_only_user: User,
) -> None:
    """Only an explicit operation gives someone a local account (ADR-0076 §6)."""
    headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    updated = client.put(
        f"/api/admin/users/{sso_only_user.id}",
        headers=headers,
        json={
            "email": _SSO_ONLY,
            "username": "SSO only",
            "is_active": True,
            "roles": [],
            "password": "given-on-purpose-1",
        },
    )
    assert updated.status_code == 200, updated.text
    signed_in = other_client.post("/api/auth/login", json={"email": _SSO_ONLY, "password": "given-on-purpose-1"})
    assert signed_in.status_code == 200, signed_in.text
