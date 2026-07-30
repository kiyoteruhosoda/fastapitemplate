from fastapi.testclient import TestClient


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
