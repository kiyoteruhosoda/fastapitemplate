from fastapi.testclient import TestClient

from tests.conftest import sign_in


def test_role_crud(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/roles",
        headers=admin_headers,
        json={"name": "item-reader", "permissions": ["item:view", "dashboard:view"]},
    )
    assert response.status_code == 201, response.text
    role_id = response.json()["id"]
    assert response.json()["permissions"] == ["dashboard:view", "item:view"]

    response = client.put(
        f"/api/admin/roles/{role_id}",
        headers=admin_headers,
        json={"permissions": ["item:view"]},
    )
    assert response.status_code == 200
    assert response.json()["permissions"] == ["item:view"]

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
    """Signs in on a **separate client** as a "user clerk" holding only ``user:manage``.

    The session is held in a cookie (ADR-0076 §4), so signing in on the same client as the
    administrator would replace the administrator's session.
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
    """To assign roles to users, one must be able to read which roles exist."""
    headers = _sign_in_user_manager(client, other_client, admin_headers)

    response = client.get("/api/admin/roles", headers=headers)

    assert response.status_code == 200
    assert "member" in [role["name"] for role in response.json()]


def test_user_manager_cannot_change_roles(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """Readable but not changeable (granting stays with role:manage)."""
    headers = _sign_in_user_manager(client, other_client, admin_headers)
    role_id = next(r["id"] for r in client.get("/api/admin/roles", headers=headers).json() if r["name"] == "member")

    assert client.post("/api/admin/roles", headers=headers, json={"name": "x"}).status_code == 403
    assert client.put(f"/api/admin/roles/{role_id}", headers=headers, json={"name": "y"}).status_code == 403
    assert client.delete(f"/api/admin/roles/{role_id}", headers=headers).status_code == 403


def test_role_catalog_still_requires_a_permission(
    client: TestClient, other_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """The "any of" relaxation is only between the two scopes; it does not open to people without permission."""
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


def test_renaming_a_role_to_a_name_in_use_is_a_conflict(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Hitting the unique constraint does not give 500; it is refused with the same 409 as on create (task #762)."""
    created = client.post(
        "/api/admin/roles",
        headers=admin_headers,
        json={"name": "item-reader", "permissions": ["item:view", "dashboard:view"]},
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["id"]

    taken = client.put(f"/api/admin/roles/{role_id}", headers=admin_headers, json={"name": "member"})
    assert taken.status_code == 409
    assert taken.json()["detail"]["error"] == "role_already_exists"
    same = client.put(f"/api/admin/roles/{role_id}", headers=admin_headers, json={"name": "item-reader"})
    assert same.status_code == 200, same.text
