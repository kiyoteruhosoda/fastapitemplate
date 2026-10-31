import pytest
from fastapi.testclient import TestClient

from shared.domain.page import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


def test_items_require_authentication(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/items", json={"name": "x"}).status_code == 401


def test_create_and_list_items(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post("/api/items", headers=admin_headers, json={"name": "alpha"})
    assert response.status_code == 201
    assert response.json()["name"] == "alpha"

    client.post("/api/items", headers=admin_headers, json={"name": "beta"})
    response = client.get("/api/items", headers=admin_headers)
    assert response.status_code == 200
    names = [item["name"] for item in response.json()["entries"]]
    assert names == ["alpha", "beta"]


def _add(client: TestClient, headers: dict[str, str], count: int) -> None:
    for number in range(count):
        assert client.post("/api/items", headers=headers, json={"name": f"item-{number}"}).status_code == 201


def test_the_list_returns_the_requested_range_and_the_total(client: TestClient, admin_headers: dict[str, str]) -> None:
    _add(client, admin_headers, 5)

    body = client.get("/api/items?limit=2&offset=2").json()
    assert body["total"] == 5
    assert [item["name"] for item in body["entries"]] == ["item-2", "item-3"]

    beyond = client.get("/api/items?limit=2&offset=10").json()
    assert beyond == {"entries": [], "total": 5}


def test_the_list_has_a_default_size(client: TestClient, admin_headers: dict[str, str]) -> None:
    _add(client, admin_headers, DEFAULT_PAGE_SIZE + 1)
    body = client.get("/api/items").json()
    assert len(body["entries"]) == DEFAULT_PAGE_SIZE
    assert body["total"] == DEFAULT_PAGE_SIZE + 1


@pytest.mark.parametrize("query", [f"limit={MAX_PAGE_SIZE + 1}", "limit=0", "limit=-1", "offset=-1", "limit=x"])
def test_a_range_out_of_the_rule_is_refused(client: TestClient, admin_headers: dict[str, str], query: str) -> None:
    assert client.get(f"/api/items?{query}").status_code == 422


def test_the_largest_size_is_accepted(client: TestClient, admin_headers: dict[str, str]) -> None:
    assert client.get(f"/api/items?limit={MAX_PAGE_SIZE}").status_code == 200


def test_create_item_empty_name_rejected(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post("/api/items", headers=admin_headers, json={"name": "  "})
    assert response.status_code == 422
