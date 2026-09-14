"""「ローカル認証を持たない」をデータで表せているか（ADR-0038）。

``users.password_hash`` が NULL の利用者は、パスワードで入れない・変更できない・
**リセットでも生やせない**。持たせられるのは管理者が明示的に設定したときだけ。
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.domain.auth import master_data
from shared.infrastructure.models import PasswordResetToken, User
from tests.conftest import sign_in

_SSO_ONLY = "sso-only@example.com"


@pytest.fixture
def sso_only_user(db_session: Session) -> User:
    """SSO でしか入れない利用者（パスワードを持たない）。"""
    user = User(email=_SSO_ONLY, username="SSO only", password_hash=None, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_an_sso_user_is_provisioned_without_a_password(db_session: Session, engine: sa.Engine) -> None:
    """⚠ ランダム値で埋めない。埋めると「無い」と「誰も知らない値がある」が混ざる。"""
    from bounded_contexts.identity_federation.domain.entities.federated_account import (
        NewFederatedAccount,
    )
    from bounded_contexts.identity_federation.infrastructure.sql_federated_user_directory import (
        SqlFederatedUserDirectory,
    )

    directory = SqlFederatedUserDirectory(db_session)
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
    """⚠ ここが抜けると、リセット 1 回でローカル認証が生える。"""
    response = client.post("/api/auth/forgot-password", json={"email": _SSO_ONLY})
    # 応答は宛先が無いときと同じ（存在を漏らさない）。
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == sso_only_user.id)) is None


def _take_the_password_away(db_session: Session, email: str) -> None:
    """入っている人のパスワードだけを取り上げる（セッションはそのまま）。

    「SSO でしか入れない利用者が、既にこのアプリに入っている」状態を作るための
    最短路。**入る手段が無い相手は、そのままではログインさせられない。**
    """
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.password_hash = None
    db_session.commit()


def test_the_screen_is_told_whether_there_is_a_password(client: TestClient, db_session: Session) -> None:
    """画面はこれを見て、パスワード変更の導線を出すかどうかを決める。"""
    sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    assert client.get("/api/auth/me").json()["has_password"] is True

    _take_the_password_away(db_session, master_data.DEFAULT_ADMIN_EMAIL)
    assert client.get("/api/auth/me").json()["has_password"] is False


def test_a_user_without_a_password_cannot_change_one(client: TestClient, db_session: Session) -> None:
    """パスワードを持たない利用者に「今のパスワード」は入力できない。

    理由は分けずに ``invalid_current_password`` へ揃える（入り口の有無を
    外から数えられないようにするため）。
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
    """ローカル口座を持たせるのは、明示的な操作だけ（ADR-0038）。"""
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
