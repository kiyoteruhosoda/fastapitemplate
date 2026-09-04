from fastapi.testclient import TestClient

from tests.conftest import sign_in


def test_role_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/roles",
        headers=admin_headers,
        json={"name": "auditor", "permissions": ["log:view", "dashboard:view"]},
    )
    assert response.status_code == 201, response.text
    role_id = response.json()["id"]
    assert response.json()["permissions"] == ["dashboard:view", "log:view"]

    response = client.put(
        f"/api/admin/roles/{role_id}",
        headers=admin_headers,
        json={"permissions": ["log:view"]},
    )
    assert response.status_code == 200
    assert response.json()["permissions"] == ["log:view"]

    assert client.delete(f"/api/admin/roles/{role_id}", headers=admin_headers).status_code == 204


def test_unknown_permission_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/roles",
        headers=admin_headers,
        json={"name": "broken", "permissions": ["no:such-code"]},
    )
    assert response.status_code == 400


def test_permission_list(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/admin/permissions", headers=admin_headers)
    assert response.status_code == 200
    codes = [p["code"] for p in response.json()]
    assert "user:manage" in codes


def _sign_in_user_manager(
    client: TestClient, manager_client: TestClient, admin_headers: dict[str, str]
) -> dict[str, str]:
    """``user:manage`` だけを持つ「ユーザー係」で**別のクライアント**にサインインする。

    セッションは Cookie で持つので（ADR-0028）、管理者と同じクライアントで
    ログインすると管理者のセッションが置き換わってしまう。
    """
    created = client.post(
        "/api/admin/roles",
        headers=admin_headers,
        json={"name": "user-manager", "permissions": ["user:manage", "dashboard:view"]},
    )
    assert created.status_code == 201, created.text
    added = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "user-manager@example.com",
            "username": "user-manager",
            "password": "password-123",
            "roles": ["user-manager"],
        },
    )
    assert added.status_code == 201, added.text
    return sign_in(manager_client, "user-manager@example.com", "password-123")


def test_user_manager_can_read_the_role_catalog(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """ユーザーへロールを割り当てるには、どんなロールがあるか読めなければならない。"""
    headers = _sign_in_user_manager(client, other_client, admin_headers)

    response = client.get("/api/admin/roles", headers=headers)

    assert response.status_code == 200
    assert "member" in [role["name"] for role in response.json()]


def test_user_manager_cannot_change_roles(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """読めても変えられない（権限を配る側は role:manage のまま）。"""
    headers = _sign_in_user_manager(client, other_client, admin_headers)
    role_id = next(r["id"] for r in client.get("/api/admin/roles", headers=headers).json() if r["name"] == "member")

    assert client.post("/api/admin/roles", headers=headers, json={"name": "x"}).status_code == 403
    assert client.put(f"/api/admin/roles/{role_id}", headers=headers, json={"name": "y"}).status_code == 403
    assert client.delete(f"/api/admin/roles/{role_id}", headers=headers).status_code == 403


def test_role_catalog_still_requires_a_permission(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """「いずれか」に緩めたのは 2 つの scope の間だけで、無権限には開かない。"""
    added = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "guest-only@example.com",
            "username": "guest-only",
            "password": "password-123",
            "roles": ["guest"],
        },
    )
    assert added.status_code == 201, added.text
    sign_in(other_client, "guest-only@example.com", "password-123")

    response = other_client.get("/api/admin/roles")

    assert response.status_code == 403
