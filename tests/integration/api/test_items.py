def test_items_require_authentication(client) -> None:
    client.cookies.clear()
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/items", json={"name": "x"}).status_code == 401


def test_create_and_list_items(client, admin_headers) -> None:
    response = client.post("/api/items", headers=admin_headers, json={"name": "alpha"})
    assert response.status_code == 201
    assert response.json()["name"] == "alpha"

    client.post("/api/items", headers=admin_headers, json={"name": "beta"})
    response = client.get("/api/items", headers=admin_headers)
    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["alpha", "beta"]


def test_create_item_empty_name_rejected(client, admin_headers) -> None:
    response = client.post("/api/items", headers=admin_headers, json={"name": "  "})
    assert response.status_code == 422
