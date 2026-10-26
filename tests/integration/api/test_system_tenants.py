"""テナントの外側の管理（ADR-0061・ADR-0065）。

システム管理者がテナントを登録・停止・削除し、最初のテナント管理者を指名する。指名された人は
招待のメールで自分のパスワードを決めるか、テナントの IdP で初めて入ったときに席を受け取る。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.email_sender import IEmailSender
from bounded_contexts.example.infrastructure.item_model import ItemModel
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
)
from bounded_contexts.identity_federation.presentation import dependencies
from presentation.fastapi.services.password_reset_service import PasswordResetService
from shared.domain.auth import master_data
from shared.infrastructure.models import Role, Tenant, User
from shared.infrastructure.tenant_directory import DEFAULT_TENANT_SLUG
from shared.kernel.database.db import Base
from tests.conftest import SYSTEM_ADMIN_EMAIL, sign_in

_ACME = {
    "slug": "acme",
    "display_name": "Acme",
    "first_admin": {"email": "boss@acme.example", "username": "boss"},
}


def _create(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/system/tenants", json={**_ACME, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_only_system_administrators_manage_tenants(client: TestClient, admin_headers: dict[str, str]) -> None:
    """テナント管理者（owner）はテナントの外側に入れない。"""
    assert client.get("/api/system/tenants").status_code == 403
    assert client.post("/api/system/tenants", json=_ACME, headers=admin_headers).status_code == 403
    assert client.get("/api/system/administrators").status_code == 403


def test_a_tenant_is_registered_with_a_designated_administrator(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    created = _create(client, system_admin_headers)
    assert created["tenant"]["slug"] == "acme"
    # 試験ではメールを止めてあるので送れない（送れたかは画面に出す）
    assert created["designation"]["invitation_sent"] is False

    with Session(engine) as session:
        seat = session.get(User, created["designation"]["user_id"])
        assert seat is not None
        assert seat.tenant_id == created["tenant"]["id"]
        assert seat.role_names == ("owner",)
        # ⚠ 指名した人はパスワードを決めない（中身を見ない約束。ADR-0065）
        assert seat.password_hash is None

    listed = {t["slug"]: t for t in client.get("/api/system/tenants").json()}
    assert listed["acme"]["member_count"] == 1
    assert "users" not in listed["acme"]


def test_slug_and_issuer_belong_to_one_tenant(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    _create(client, system_admin_headers, issuer="https://idp.example.test/acme", client_id="rp")
    again = client.post("/api/system/tenants", json=_ACME, headers=system_admin_headers)
    assert again.status_code == 409
    same_issuer = client.post(
        "/api/system/tenants",
        json={**_ACME, "slug": "acme2", "issuer": "https://idp.example.test/acme"},
        headers=system_admin_headers,
    )
    assert same_issuer.json()["detail"]["error"] == "issuer_already_registered"


@dataclass
class _Outbox(IEmailSender):
    sent: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def test_the_invitation_lets_the_designated_person_choose_a_password(
    client: TestClient,
    other_client: TestClient,
    system_admin_headers: dict[str, str],
    engine: sa.Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _create(client, system_admin_headers)
    monkeypatch.setenv("MAIL_ENABLED", "true")
    outbox = _Outbox()
    with Session(engine) as session:
        seat = session.get(User, created["designation"]["user_id"])
        assert seat is not None
        assert PasswordResetService(sender=outbox).invite(session, seat, place="Acme") is True
        session.commit()
    token = outbox.sent[0].body.split("token=")[1].split()[0]

    chosen = other_client.post("/api/auth/reset-password", json={"token": token, "new_password": "boss-password-1"})
    assert chosen.status_code == 200, chosen.text
    response = other_client.post(
        "/api/auth/login", json={"email": "boss@acme.example", "password": "boss-password-1", "tenant": "acme"}
    )
    assert response.status_code == 200, response.text
    assert "user:manage" in other_client.get("/api/auth/me").json()["scopes"]


def test_a_suspended_tenant_cannot_sign_in_and_only_then_can_be_deleted(
    client: TestClient, other_client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    default_id = next(t["id"] for t in client.get("/api/system/tenants").json() if t["slug"] == "default")

    assert client.delete(f"/api/system/tenants/{default_id}", headers=system_admin_headers).status_code == 409
    suspended = client.put(
        f"/api/system/tenants/{default_id}", json={"status": "suspended"}, headers=system_admin_headers
    )
    assert suspended.json()["status"] == "suspended"

    refused = other_client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["error"] == "tenant_suspended"

    assert client.delete(f"/api/system/tenants/{default_id}", headers=system_admin_headers).status_code == 204
    with Session(engine) as session:
        assert session.get(Tenant, default_id) is None
        assert session.scalar(sa.select(User).where(User.email == master_data.DEFAULT_ADMIN_EMAIL)) is None


def test_system_administrators_are_added_by_invitation_and_never_all_removed(
    client: TestClient, system_admin_headers: dict[str, str]
) -> None:
    added = client.post(
        "/api/system/administrators",
        json={"email": "second@ops.example", "username": "second"},
        headers=system_admin_headers,
    )
    assert added.status_code == 201, added.text
    listed = client.get("/api/system/administrators").json()
    assert {a["email"] for a in listed} >= {"second@ops.example"}
    me = client.get("/api/auth/me").json()["user_id"]

    assert client.delete(f"/api/system/administrators/{me}", headers=system_admin_headers).status_code == 403
    removed = client.delete(f"/api/system/administrators/{added.json()['user_id']}", headers=system_admin_headers)
    assert removed.status_code == 204


# --- 指名された席を IdP で受け取る（ADR-0065） ----------------------------------

_ISSUER = "https://idp.example.test/acme"


@dataclass
class _StubGateway:
    email: str

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{request.provider.issuer}/authorize?state={request.state}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        return {"sub": "boss-subject", "email": self.email, "email_verified": True, "name": "Boss"}


@pytest.fixture
def sso_app(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shhh")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://app.example.test/api/auth/sso/callback")
    # ⚠ 寄せる設定（OIDC_LINK_BY_EMAIL）は既定の「寄せない」のまま。席はそれとは別に受け取れる
    app.dependency_overrides[dependencies.oidc_gateway] = lambda: _StubGateway("boss@acme.example")
    yield app
    app.dependency_overrides.clear()


def test_the_designated_seat_is_claimed_at_the_first_sso_sign_in(
    sso_app: FastAPI, client: TestClient, system_admin_headers: dict[str, str]
) -> None:
    created = _create(client, system_admin_headers, issuer=_ISSUER, client_id="acme-rp")
    with TestClient(sso_app) as browser:
        started = browser.get("/api/auth/sso/login", params={"tenant": "acme"}, follow_redirects=False)
        state = started.headers["location"].split("state=")[1]
        done = browser.get("/api/auth/sso/callback", params={"code": "c", "state": state}, follow_redirects=False)
        ticket = done.headers["location"].split("ticket=")[1]
        assert browser.post("/api/auth/sso/token", json={"ticket": ticket}).status_code == 200
        me = browser.get("/api/auth/me").json()
    assert me["user_id"] == created["designation"]["user_id"]
    assert "owner" in me["roles"]


def test_a_seat_someone_already_uses_is_not_taken_over(
    sso_app: FastAPI, client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """入り口を持った利用者は「席」ではない。寄せる設定が無ければ断る（ADR-0037）。"""
    created = _create(client, system_admin_headers, issuer=_ISSUER, client_id="acme-rp")
    with Session(engine) as session:
        seat = session.get(User, created["designation"]["user_id"])
        assert seat is not None
        seat.password_hash = generate_password_hash("boss-password-1")
        session.commit()
    with TestClient(sso_app) as browser:
        started = browser.get("/api/auth/sso/login", params={"tenant": "acme"}, follow_redirects=False)
        state = started.headers["location"].split("state=")[1]
        done = browser.get("/api/auth/sso/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert "sso_error=sso_account_not_linked" in done.headers["location"]


# --- 消す・変える・指名し直す -------------------------------------------------

_BOSS_PASSWORD = "boss-password-1"


def _sign_in_as_the_boss(browser: TestClient, engine: sa.Engine, seat_id: int) -> dict[str, str]:
    """指名された席にパスワードを持たせ、そのテナントの入口から入る（招待の往復は上の試験で見ている）。"""
    with Session(engine) as session:
        seat = session.get(User, seat_id)
        assert seat is not None
        seat.password_hash = generate_password_hash(_BOSS_PASSWORD)
        session.commit()
    return sign_in(browser, "boss@acme.example", _BOSS_PASSWORD, tenant="acme")


def _fill_the_tenant(browser: TestClient, headers: dict[str, str]) -> None:
    """テナントの管理者として、各コンテキストに中身を作る。"""
    member = browser.post(
        "/api/admin/users",
        json={"email": "kid@acme.example", "username": "kid", "password": "member-password-1", "roles": ["member"]},
        headers=headers,
    )
    assert member.status_code == 201, member.text
    created = [
        browser.post("/api/items", json={"name": "acme-item"}, headers=headers),
        browser.post("/api/admin/groups", json={"name": "家族", "member_ids": [member.json()["id"]]}, headers=headers),
        browser.post("/api/admin/roles", json={"name": "acme-reader", "permissions": ["item:view"]}, headers=headers),
        browser.post(
            "/api/admin/notifications",
            json={"title": "acme", "channels": ["bell"], "audience": {"kind": "all"}},
            headers=headers,
        ),
    ]
    assert [r.status_code for r in created] == [201] * len(created), [r.text for r in created]


def _rows_of(session: Session, tenant_id: int) -> dict[str, int]:
    """``tenant_id`` を持つ表ごとの、そのテナントの行数（0 の表は省く）。"""
    counts = {
        table.name: session.scalar(sa.select(sa.func.count()).select_from(table).where(table.c.tenant_id == tenant_id))
        or 0
        for table in Base.metadata.sorted_tables
        if "tenant_id" in table.columns
    }
    return {name: count for name, count in counts.items() if count}


def test_deleting_a_tenant_takes_its_people_and_content_but_keeps_the_audit_trail(
    app: FastAPI, client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """消すと戻せないので、消えるもの・残るもの・巻き込まないものを表ごとに確かめる（ADR-0065）。"""
    created = _create(client, system_admin_headers)
    acme_id = created["tenant"]["id"]
    with TestClient(app) as boss, TestClient(app) as neighbour:
        _fill_the_tenant(boss, _sign_in_as_the_boss(boss, engine, created["designation"]["user_id"]))
        neighbour_headers = sign_in(
            neighbour,
            master_data.DEFAULT_ADMIN_EMAIL,
            master_data.DEFAULT_ADMIN_PASSWORD,
            tenant=DEFAULT_TENANT_SLUG,
        )
        assert (
            neighbour.post("/api/items", json={"name": "neighbour-item"}, headers=neighbour_headers).status_code == 201
        )

    with Session(engine) as session:
        before = _rows_of(session, acme_id)
    # 中身が本当に入っていること（入っていなければ、消えたかどうかを見ていない）
    assert {"items", "user_groups", "role_tenants", "notifications", "audit_log"} <= before.keys()

    suspended = client.put(f"/api/system/tenants/{acme_id}", json={"status": "suspended"}, headers=system_admin_headers)
    assert suspended.status_code == 200, suspended.text
    assert client.delete(f"/api/system/tenants/{acme_id}", headers=system_admin_headers).status_code == 204

    with Session(engine) as session:
        # 監査ログだけが残る（誰が何をしたかは、テナントを消しても追える。ADR-0013）
        assert set(_rows_of(session, acme_id)) == {"audit_log"}
        assert (
            session.scalar(
                sa.select(sa.func.count()).select_from(AuditLogModel).where(AuditLogModel.tenant_id == acme_id)
            )
            == before["audit_log"]
        )
        emails = set(session.scalars(sa.select(User.email)))
        assert not emails & {"boss@acme.example", "kid@acme.example"}
        assert session.scalar(sa.select(Role).where(Role.name == "acme-reader")) is None
        # 隣のテナントは巻き込まない
        assert master_data.DEFAULT_ADMIN_EMAIL in emails
        assert session.scalar(sa.select(ItemModel).where(ItemModel.name == "neighbour-item")) is not None
        # 共有のロール（雛形）は消さない
        assert session.scalar(sa.select(Role).where(Role.name == master_data.DEFAULT_ADMIN_ROLE)) is not None


def test_a_tenant_can_be_renamed_and_rewired(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    tenant_id = _create(client, system_admin_headers)["tenant"]["id"]
    changed = client.put(
        f"/api/system/tenants/{tenant_id}",
        json={"display_name": "  Acme Inc.  ", "issuer": "https://idp.example.test/acme/", "client_id": "acme-rp"},
        headers=system_admin_headers,
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["display_name"], body["issuer"], body["client_id"]) == (
        "Acme Inc.",
        "https://idp.example.test/acme",
        "acme-rp",
    )
    # 自分の発行者をそのまま送り直しても、自分とはぶつからない
    again = client.put(
        f"/api/system/tenants/{tenant_id}",
        json={"issuer": "https://idp.example.test/acme"},
        headers=system_admin_headers,
    )
    assert again.status_code == 200, again.text
    # 空にすれば SSO を使わないテナントに戻る
    cleared = client.put(
        f"/api/system/tenants/{tenant_id}", json={"issuer": "", "client_id": ""}, headers=system_admin_headers
    ).json()
    assert (cleared["issuer"], cleared["client_id"]) == (None, None)


def test_an_issuer_another_tenant_uses_cannot_be_taken_by_an_update(
    client: TestClient, system_admin_headers: dict[str, str]
) -> None:
    _create(client, system_admin_headers, issuer="https://idp.example.test/acme", client_id="rp")
    other = _create(
        client, system_admin_headers, slug="beta", first_admin={"email": "boss@beta.example", "username": "boss"}
    )
    taken = client.put(
        f"/api/system/tenants/{other['tenant']['id']}",
        json={"issuer": "https://idp.example.test/acme/"},
        headers=system_admin_headers,
    )
    assert taken.status_code == 409
    assert taken.json()["detail"]["error"] == "issuer_already_registered"


def test_an_unknown_tenant_is_not_found(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    designation = {"email": "boss@nowhere.example", "username": "boss"}
    responses = [
        client.put("/api/system/tenants/9999", json={"status": "suspended"}, headers=system_admin_headers),
        client.delete("/api/system/tenants/9999", headers=system_admin_headers),
        client.post("/api/system/tenants/9999/administrators", json=designation, headers=system_admin_headers),
    ]
    assert [r.status_code for r in responses] == [404, 404, 404]
    assert {r.json()["detail"]["error"] for r in responses} == {"tenant_not_found"}


def test_another_tenant_administrator_can_be_designated(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """管理者が居なくなったときの立て直し。新しい席を作って招待する（今いる人を上げはしない）。"""
    tenant_id = _create(client, system_admin_headers)["tenant"]["id"]
    second = client.post(
        f"/api/system/tenants/{tenant_id}/administrators",
        json={"email": "deputy@acme.example", "username": "deputy"},
        headers=system_admin_headers,
    )
    assert second.status_code == 201, second.text
    with Session(engine) as session:
        seat = session.get(User, second.json()["user_id"])
        assert seat is not None
        assert (seat.tenant_id, seat.role_names, seat.password_hash) == (tenant_id, ("owner",), None)

    listed = {t["slug"]: t for t in client.get("/api/system/tenants").json()}
    assert listed["acme"]["member_count"] == 2

    # 同じテナントに同じメールアドレスの人は置けない。ほかのテナントなら置ける（一意はテナントの中だけ）
    duplicate = client.post(
        f"/api/system/tenants/{tenant_id}/administrators",
        json={"email": "deputy@acme.example", "username": "deputy2"},
        headers=system_admin_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error"] == "email_already_exists"
    default_id = listed["default"]["id"]
    elsewhere = client.post(
        f"/api/system/tenants/{default_id}/administrators",
        json={"email": "deputy@acme.example", "username": "deputy"},
        headers=system_admin_headers,
    )
    assert elsewhere.status_code == 201, elsewhere.text


def test_a_tenant_administrator_cannot_designate_one(client: TestClient, admin_headers: dict[str, str]) -> None:
    designation = {"email": "deputy@example.com", "username": "deputy"}
    assert (
        client.post("/api/system/tenants/1/administrators", json=designation, headers=admin_headers).status_code == 403
    )
    assert client.put("/api/system/tenants/1", json={"status": "suspended"}, headers=admin_headers).status_code == 403
    assert client.delete("/api/system/tenants/1", headers=admin_headers).status_code == 403


def test_a_system_administrator_email_is_used_once(client: TestClient, system_admin_headers: dict[str, str]) -> None:
    taken = client.post(
        "/api/system/administrators",
        json={"email": SYSTEM_ADMIN_EMAIL, "username": "again"},
        headers=system_admin_headers,
    )
    assert taken.status_code == 409
    assert taken.json()["detail"]["error"] == "email_already_exists"


def test_only_system_administrators_are_removed_here(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    """この口でテナントの人は消せない（テナントの中の人事はテナント管理者の仕事）。"""
    with Session(engine) as session:
        tenant_member = session.scalar(sa.select(User.id).where(User.email == master_data.DEFAULT_ADMIN_EMAIL))
    for user_id in (tenant_member, 9999):
        refused = client.delete(f"/api/system/administrators/{user_id}", headers=system_admin_headers)
        assert refused.status_code == 404
        assert refused.json()["detail"]["error"] == "user_not_found"
    with Session(engine) as session:
        assert session.get(User, tenant_member) is not None


def test_the_tenant_ledger_is_audited(
    client: TestClient, system_admin_headers: dict[str, str], engine: sa.Engine
) -> None:
    created = _create(client, system_admin_headers)
    tenant_id = created["tenant"]["id"]
    client.put(f"/api/system/tenants/{tenant_id}", json={"status": "suspended"}, headers=system_admin_headers)
    client.delete(f"/api/system/tenants/{tenant_id}", headers=system_admin_headers)
    added = client.post(
        "/api/system/administrators",
        json={"email": "second@ops.example", "username": "second"},
        headers=system_admin_headers,
    ).json()["user_id"]
    client.delete(f"/api/system/administrators/{added}", headers=system_admin_headers)

    with Session(engine) as session:
        recorded = {
            (row.event_type, row.target_type, row.target_id, row.reason)
            for row in session.scalars(sa.select(AuditLogModel))
        }
    expected = {
        (AuditEventType.TENANT_CREATED.value, "tenant", str(tenant_id), None),
        (AuditEventType.TENANT_UPDATED.value, "tenant", str(tenant_id), "fields=status"),
        (AuditEventType.TENANT_DELETED.value, "tenant", str(tenant_id), None),
        (
            AuditEventType.TENANT_ADMIN_DESIGNATED.value,
            "user",
            str(created["designation"]["user_id"]),
            f"tenant={tenant_id} invitation_sent=false",
        ),
        (AuditEventType.SYSTEM_ADMIN_ADDED.value, "user", str(added), None),
        (AuditEventType.SYSTEM_ADMIN_REMOVED.value, "user", str(added), None),
    }
    assert expected <= recorded
