"""「この利用者が入れる手段」の棚卸し（ADR-0039）。

認証系が 2 つある以上、開いている口の数は**並べて見ないと分からない**。
材料はそれぞれのコンテキストが答える（パスワード / TOTP・パスキー / IdP との結び付き）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.account_security.infrastructure.account_security_models import (
    PasskeyCredentialRecord,
    TotpSecretRecord,
)
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    FederatedIdentityRecord,
)
from shared.domain.auth import master_data
from shared.infrastructure.models import User
from shared.kernel.timestamps import utcnow
from tests.conftest import sign_in

_ISSUER = "https://idp.example.test"


def _entrances_of(client: TestClient, headers: dict[str, str], email: str) -> dict[str, object]:
    listed = client.get("/api/admin/users", headers=headers)
    assert listed.status_code == 200, listed.text
    row = next(user for user in listed.json() if user["email"] == email)
    entrances: dict[str, object] = row["entrances"]
    return entrances


def test_a_password_only_user_shows_one_entrance(client: TestClient) -> None:
    headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    assert _entrances_of(client, headers, master_data.DEFAULT_ADMIN_EMAIL) == {
        "password": True,
        "totp": False,
        "passkeys": 0,
        "identity_providers": [],
    }


def test_every_entrance_is_listed(client: TestClient, db_session: Session) -> None:
    """⚠ IdP 側の多要素はここに出ない。出せるのはこのアプリが知っている口だけ。"""
    headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    admin = db_session.scalar(select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    assert admin is not None
    db_session.add(TotpSecretRecord(user_id=admin.id, secret="s", confirmed_at=utcnow()))
    db_session.add(
        PasskeyCredentialRecord(
            credential_id="c1",
            user_id=admin.id,
            public_key="k",
            sign_count=0,
            name="laptop",
        )
    )
    db_session.add(FederatedIdentityRecord(issuer=_ISSUER, subject="sub", user_id=admin.id))
    db_session.commit()

    assert _entrances_of(client, headers, master_data.DEFAULT_ADMIN_EMAIL) == {
        "password": True,
        "totp": True,
        "passkeys": 1,
        "identity_providers": [_ISSUER],
    }


def test_an_enrolment_in_progress_is_not_an_entrance(client: TestClient, db_session: Session) -> None:
    """登録手続きの途中（``confirmed_at`` が NULL）は、まだ入り口ではない。"""
    headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    admin = db_session.scalar(select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    assert admin is not None
    db_session.add(TotpSecretRecord(user_id=admin.id, secret="s", confirmed_at=None))
    db_session.commit()

    assert _entrances_of(client, headers, master_data.DEFAULT_ADMIN_EMAIL)["totp"] is False


def test_a_user_without_a_password_shows_only_what_is_left(client: TestClient, db_session: Session) -> None:
    """⚠ パスワードを取り上げても、結び付きが残っていれば SSO では入れる。"""
    headers = sign_in(client, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    admin = db_session.scalar(select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    assert admin is not None
    db_session.add(FederatedIdentityRecord(issuer=_ISSUER, subject="sub", user_id=admin.id))
    admin.password_hash = None
    db_session.commit()

    assert _entrances_of(client, headers, master_data.DEFAULT_ADMIN_EMAIL) == {
        "password": False,
        "totp": False,
        "passkeys": 0,
        "identity_providers": [_ISSUER],
    }
