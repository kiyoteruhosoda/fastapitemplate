def test_create_item(client) -> None:
    response = client.post("/items", json={"name": "sample"})
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "sample"


def test_create_item_empty_name_rejected(client) -> None:
    response = client.post("/items", json={"name": "  "})
    assert response.status_code == 422


def test_list_items(client) -> None:
    client.post("/items", json={"name": "alpha"})
    client.post("/items", json={"name": "beta"})
    response = client.get("/items")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["name"] == "alpha"
    assert items[1]["name"] == "beta"


def test_list_items_empty(client) -> None:
    response = client.get("/items")
    assert response.status_code == 200
    assert response.json() == []


def test_response_has_request_id_header(client) -> None:
    response = client.get("/health")
    assert "x-request-id" in response.headers
