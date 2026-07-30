from fastapi.testclient import TestClient


def test_admin_users_require_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/users").status_code == 401


def test_user_crud_and_role_scope(client: TestClient, admin_headers: dict[str, str]) -> None:
    # 作成
    response = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "member@example.com",
            "username": "member",
            "password": "member-pass-1",
            "roles": ["member"],
        },
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert response.json()["roles"] == ["member"]

    # member ロールでは items 閲覧のみ・管理系は 403
    login = client.post(
        "/api/auth/login",
        json={"email": "member@example.com", "password": "member-pass-1"},
    )
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/items", headers=member_headers).status_code == 200
    assert client.post("/api/items", headers=member_headers, json={"name": "x"}).status_code == 403
    assert client.get("/api/admin/users", headers=member_headers).status_code == 403

    # 更新（無効化）
    response = client.put(
        f"/api/admin/users/{user_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # 削除
    assert client.delete(f"/api/admin/users/{user_id}", headers=admin_headers).status_code == 204
    users = client.get("/api/admin/users", headers=admin_headers).json()
    assert all(u["id"] != user_id for u in users)


def test_duplicate_email_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "admin@example.com",
            "username": "dup",
            "password": "whatever-123",
        },
    )
    assert response.status_code == 409


def test_unknown_role_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "email": "x@example.com",
            "username": "x",
            "password": "whatever-123",
            "roles": ["nonexistent"],
        },
    )
    assert response.status_code == 400
