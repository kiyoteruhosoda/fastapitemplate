"""2 つのテナントが互いの人と中身を見られないこと（ADR-0061 決定 5・6）。

既定のテナント（初期管理者が ``owner``）と、もう 1 つのテナント（別の ``owner``）を作り、
各コンテキストの API で「相手の行は一覧に出ず、ID を名指ししても 404」を確かめる。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.security import generate_password_hash

from shared.domain.auth import master_data
from shared.infrastructure.administrator_census import count_active_administrators
from shared.infrastructure.models import Role, Tenant, User
from tests.conftest import sign_in

_OTHER_EMAIL = "owner@other.example"
_OTHER_PASSWORD = "other-owner-password-1"


def _seed_other_tenant(engine: sa.Engine) -> None:
    with sessionmaker(bind=engine)() as session:
        tenant = Tenant(slug="other", display_name="Other")
        session.add(tenant)
        session.flush()
        owner = User(
            email=_OTHER_EMAIL,
            username="other-owner",
            password_hash=generate_password_hash(_OTHER_PASSWORD),
            is_active=True,
        )
        owner.roles = [session.scalars(sa.select(Role).where(Role.name == master_data.DEFAULT_ADMIN_ROLE)).one()]
        owner.join(tenant.id)
        session.add(owner)
        session.commit()


@pytest.fixture
def other(app: FastAPI, engine: sa.Engine) -> Iterator[tuple[TestClient, dict[str, str]]]:
    """もう 1 つのテナントの管理者（別のブラウザ）。"""
    _seed_other_tenant(engine)
    with TestClient(app) as c:
        yield c, sign_in(c, _OTHER_EMAIL, _OTHER_PASSWORD)


@pytest.fixture
def mine(client: TestClient, admin_headers: dict[str, str]) -> tuple[TestClient, dict[str, str]]:
    """既定のテナントの管理者。"""
    return client, admin_headers


Side = tuple[TestClient, dict[str, str]]


def _create_member(side: Side, name: str) -> int:
    client, headers = side
    response = client.post(
        "/api/admin/users",
        json={"email": f"{name}@example.com", "username": name, "password": "member-password-1", "roles": ["member"]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_items_stay_in_their_tenant(mine: Side, other: Side) -> None:
    client, headers = mine
    assert client.post("/api/items", json={"name": "mine"}, headers=headers).status_code == 201

    other_client, other_headers = other
    assert other_client.post("/api/items", json={"name": "theirs"}, headers=other_headers).status_code == 201

    assert [i["name"] for i in client.get("/api/items").json()] == ["mine"]
    assert [i["name"] for i in other_client.get("/api/items").json()] == ["theirs"]


def test_people_stay_in_their_tenant(mine: Side, other: Side) -> None:
    member_id = _create_member(mine, "alice")
    other_client, other_headers = other

    listed = {u["email"] for u in other_client.get("/api/admin/users").json()}
    assert listed == {_OTHER_EMAIL}

    update = other_client.put(f"/api/admin/users/{member_id}", json={"username": "x"}, headers=other_headers)
    assert update.status_code == 404
    delete = other_client.delete(f"/api/admin/users/{member_id}", headers=other_headers)
    assert delete.status_code == 404


def test_groups_stay_in_their_tenant(mine: Side, other: Side) -> None:
    client, headers = mine
    member_id = _create_member(mine, "bob")
    group = client.post("/api/admin/groups", json={"name": "家族", "member_ids": [member_id]}, headers=headers)
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    other_client, other_headers = other
    # 同じ名前を、別のテナントでも作れる（相手の名前とぶつからない）
    assert other_client.post("/api/admin/groups", json={"name": "家族"}, headers=other_headers).status_code == 201
    assert [g["id"] for g in other_client.get("/api/admin/groups").json()] != [group_id]
    assert other_client.get("/api/admin/groups/users").json() == [
        {"id": u["id"], "username": u["username"], "email": u["email"]}
        for u in other_client.get("/api/admin/groups/users").json()
        if u["email"] == _OTHER_EMAIL
    ]
    update = other_client.put(f"/api/admin/groups/{group_id}", json={"name": "x"}, headers=other_headers)
    assert update.status_code == 404
    # 相手の利用者を自分のグループへ入れることもできない
    stolen = other_client.post(
        "/api/admin/groups", json={"name": "盗む", "member_ids": [member_id]}, headers=other_headers
    )
    assert stolen.status_code == 400


def test_notifications_stay_in_their_tenant(mine: Side, other: Side) -> None:
    client, headers = mine
    member_id = _create_member(mine, "carol")
    sent = client.post(
        "/api/admin/notifications",
        json={"title": "mine", "channels": ["bell"], "audience": {"kind": "all"}},
        headers=headers,
    )
    assert sent.status_code == 201, sent.text

    other_client, other_headers = other
    assert other_client.get("/api/admin/notifications").json() == []
    options = other_client.get("/api/admin/notifications/audiences").json()
    assert {u["email"] for u in options["users"]} == {_OTHER_EMAIL}
    # 相手の利用者を名指しして送ることはできない
    aimed = other_client.post(
        "/api/admin/notifications",
        json={"title": "x", "channels": ["bell"], "audience": {"kind": "user", "target_id": member_id}},
        headers=other_headers,
    )
    assert aimed.status_code == 404
    # 「全員」は自分のテナントの全員だけ
    everyone = other_client.post(
        "/api/admin/notifications",
        json={"title": "theirs", "channels": ["bell"], "audience": {"kind": "all"}},
        headers=other_headers,
    )
    assert everyone.json()["recipient_count"] == 1


def test_audit_logs_stay_in_their_tenant(mine: Side, other: Side) -> None:
    member_id = _create_member(mine, "dave")
    other_client, _ = other
    entries = other_client.get("/api/admin/audit-logs", params={"limit": 100}).json()["entries"]
    assert all(e["target_id"] != str(member_id) for e in entries)
    client, _ = mine
    mine_entries = client.get("/api/admin/audit-logs", params={"limit": 100}).json()["entries"]
    assert any(e["target_id"] == str(member_id) for e in mine_entries)


def test_the_administrators_are_counted_per_tenant(mine: Side, other: Side, engine: sa.Engine) -> None:
    """「管理の要」はテナントごとに数える。別のテナントの管理者は、自分のテナントの数に入らない。"""
    _create_member(mine, "erin")
    with Session(engine) as session:
        tenants = {t.slug: t.id for t in session.scalars(sa.select(Tenant))}
        assert count_active_administrators(session, tenants["default"]) == 1
        assert count_active_administrators(session, tenants["other"]) == 1
        assert count_active_administrators(session, None) == 0


def test_a_principal_outside_any_tenant_cannot_reach_the_content(client: TestClient, engine: sa.Engine) -> None:
    """テナントに属さない主体は、中身の口で 403（全部のテナントとして扱わない）。"""
    with sessionmaker(bind=engine)() as session:
        loner = User(
            email="loner@example.com",
            username="loner",
            password_hash=generate_password_hash("loner-password-1"),
            is_active=True,
        )
        loner.roles = [session.scalars(sa.select(Role).where(Role.name == master_data.DEFAULT_ADMIN_ROLE)).one()]
        session.add(loner)
        session.commit()
    sign_in(client, "loner@example.com", "loner-password-1")
    response = client.get("/api/items")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tenant_required"
    assert client.get("/api/admin/users").status_code == 403


# --- 外側と内側（ADR-0061 決定 4） ---------------------------------------------


def test_the_tenant_administrator_no_longer_reaches_the_whole_app(mine: Side) -> None:
    """テナント管理者（owner）は全体の設定・再起動・アプリログに入れない。"""
    client, _ = mine
    for path in ("/api/admin/config", "/api/admin/system/status", "/api/admin/logs"):
        assert client.get(path).status_code == 403, path
    scopes = set(client.get("/api/auth/me").json()["scopes"])
    assert not scopes & set(master_data.SYSTEM_PERMISSIONS)


def test_the_system_administrator_sees_no_content(
    client: TestClient, system_admin_headers: dict[str, str], other: Side
) -> None:
    """システム管理者は中身も、テナントの人も見られない。"""
    assert client.get("/api/admin/config").status_code == 200
    for path in ("/api/items", "/api/admin/users", "/api/admin/groups", "/api/admin/notifications"):
        assert client.get(path).status_code == 403, path
    # 監査ログは全体の記録だけ（テナントの人の記録は出ない）
    me = client.get("/api/auth/me").json()["user_id"]
    logins = client.get("/api/admin/audit-logs", params={"event_type": "login.succeeded"}).json()["entries"]
    assert {e["actor_user_id"] for e in logins} == {me}


def test_system_roles_are_not_offered_inside_a_tenant(mine: Side) -> None:
    client, headers = mine
    names = {r["name"] for r in client.get("/api/admin/roles").json()}
    assert "system-admin" not in names
    codes = {p["code"] for p in client.get("/api/admin/permissions").json()}
    assert not codes & set(master_data.SYSTEM_PERMISSIONS)
    granted = client.post(
        "/api/admin/users",
        json={"email": "x@example.com", "username": "x", "password": "member-password-1", "roles": ["system-admin"]},
        headers=headers,
    )
    assert granted.status_code == 400


def test_a_tenant_role_is_invisible_to_other_tenants(mine: Side, other: Side) -> None:
    client, headers = mine
    created = client.post("/api/admin/roles", json={"name": "reader", "permissions": ["item:view"]}, headers=headers)
    assert created.status_code == 201, created.text
    role_id = created.json()["id"]
    other_client, other_headers = other
    assert "reader" not in {r["name"] for r in other_client.get("/api/admin/roles").json()}
    assert (
        other_client.put(f"/api/admin/roles/{role_id}", json={"permissions": []}, headers=other_headers).status_code
        == 404
    )
    assert other_client.delete(f"/api/admin/roles/{role_id}", headers=other_headers).status_code == 404
