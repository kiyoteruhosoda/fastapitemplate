"""Two tenants cannot see each other's people or contents (ADR-0079 §1 decisions 5, 6).

Creates the default tenant (initial administrator as ``owner``) and another tenant (a different
``owner``), and checks through each context's API that "the other side's rows are not listed and
naming their ID gives 404".
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
    """The administrator of the other tenant (a separate browser)."""
    _seed_other_tenant(engine)
    with TestClient(app) as c:
        # There are now two tenants, so sign in through that tenant's entrance (ADR-0079 §4)
        yield c, sign_in(c, _OTHER_EMAIL, _OTHER_PASSWORD, tenant="other")


@pytest.fixture
def mine(client: TestClient, admin_headers: dict[str, str]) -> tuple[TestClient, dict[str, str]]:
    """The administrator of the default tenant."""
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

    assert [i["name"] for i in client.get("/api/items").json()["entries"]] == ["mine"]
    assert [i["name"] for i in other_client.get("/api/items").json()["entries"]] == ["theirs"]


def test_another_tenants_item_looks_missing(mine: Side, other: Side) -> None:
    client, headers = mine
    item_id = client.post("/api/items", json={"name": "mine"}, headers=headers).json()["id"]
    other_client, other_headers = other

    renamed = other_client.put(f"/api/items/{item_id}", json={"name": "taken"}, headers=other_headers)
    assert renamed.status_code == 404
    assert other_client.delete(f"/api/items/{item_id}", headers=other_headers).status_code == 404
    assert [i["name"] for i in client.get("/api/items").json()["entries"]] == ["mine"]


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
    # The same name can be created in another tenant (no clash with the other side's names)
    assert other_client.post("/api/admin/groups", json={"name": "家族"}, headers=other_headers).status_code == 201
    assert [g["id"] for g in other_client.get("/api/admin/groups").json()] != [group_id]
    assert other_client.get("/api/admin/groups/users").json() == [
        {"id": u["id"], "username": u["username"], "email": u["email"]}
        for u in other_client.get("/api/admin/groups/users").json()
        if u["email"] == _OTHER_EMAIL
    ]
    update = other_client.put(f"/api/admin/groups/{group_id}", json={"name": "x"}, headers=other_headers)
    assert update.status_code == 404
    # Nor can the other side's users be added to your own group
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
    # Cannot send to the other side's users by naming them
    aimed = other_client.post(
        "/api/admin/notifications",
        json={"title": "x", "channels": ["bell"], "audience": {"kind": "user", "target_id": member_id}},
        headers=other_headers,
    )
    assert aimed.status_code == 404
    # "Everyone" means only everyone in your own tenant
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
    """The "administration keystone" is counted per tenant. Another tenant's administrator does not count."""
    _create_member(mine, "erin")
    with Session(engine) as session:
        tenants = {t.slug: t.id for t in session.scalars(sa.select(Tenant))}
        assert count_active_administrators(session, tenants["default"]) == 1
        assert count_active_administrators(session, tenants["other"]) == 1
        assert count_active_administrators(session, None) == 0


def test_a_principal_outside_any_tenant_cannot_reach_the_content(client: TestClient, engine: sa.Engine) -> None:
    """A principal outside any tenant gets 403 on content entrances (it is not treated as all tenants).

    Inner roles do not take effect even if (mistakenly) assigned (ADR-0079 §3), so it is refused at the
    permission stage.
    """
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
    assert "item:view" not in client.get("/api/auth/me").json()["scopes"]
    assert client.get("/api/items").status_code == 403
    assert client.get("/api/admin/users").status_code == 403


# --- Outside and inside (ADR-0079 §1 decision 4) ---------------------------------------------


def test_the_tenant_administrator_no_longer_reaches_the_whole_app(mine: Side) -> None:
    """The tenant administrator (owner) cannot access system settings, restart or app logs."""
    client, _ = mine
    for path in ("/api/admin/config", "/api/admin/system/status", "/api/admin/logs"):
        assert client.get(path).status_code == 403, path
    scopes = set(client.get("/api/auth/me").json()["scopes"])
    assert not scopes & set(master_data.SYSTEM_PERMISSIONS)


def test_the_system_administrator_sees_no_content(
    client: TestClient, system_admin_headers: dict[str, str], other: Side
) -> None:
    """The system administrator sees neither contents nor the tenant's people."""
    assert client.get("/api/admin/config").status_code == 200
    for path in ("/api/items", "/api/admin/users", "/api/admin/groups", "/api/admin/notifications"):
        assert client.get(path).status_code == 403, path
    # Audit logs show only system-wide records (not those of the tenant's people)
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
