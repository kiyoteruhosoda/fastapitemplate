from datetime import timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bounded_contexts.example.infrastructure.item_model import ItemModel
from shared.domain.page import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from shared.kernel.timestamps import utcnow


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


def _create(client: TestClient, headers: dict[str, str], name: str = "alpha") -> int:
    response = client.post("/api/items", headers=headers, json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def test_an_item_has_its_times(client: TestClient, admin_headers: dict[str, str]) -> None:
    body = client.post("/api/items", headers=admin_headers, json={"name": "alpha"}).json()
    assert body["created_at"].endswith("Z")
    assert body["updated_at"].endswith("Z")
    assert client.get("/api/items").json()["entries"][0]["created_at"] == body["created_at"]


def test_update_changes_the_name_and_the_time(
    client: TestClient, admin_headers: dict[str, str], db_session: Session
) -> None:
    item_id = _create(client, admin_headers)
    long_ago = utcnow() - timedelta(days=1)
    db_session.execute(sa.update(ItemModel).values(created_at=long_ago, updated_at=long_ago))
    db_session.commit()

    response = client.put(f"/api/items/{item_id}", headers=admin_headers, json={"name": "renamed"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "renamed"
    assert body["updated_at"] > body["created_at"]
    assert [item["name"] for item in client.get("/api/items").json()["entries"]] == ["renamed"]


def test_delete_removes_the_item(client: TestClient, admin_headers: dict[str, str]) -> None:
    item_id = _create(client, admin_headers)
    assert client.delete(f"/api/items/{item_id}", headers=admin_headers).status_code == 204
    assert client.get("/api/items").json() == {"entries": [], "total": 0}


@pytest.mark.parametrize("name", ["", "   ", "x" * 256])
def test_a_bad_name_is_refused_on_update(client: TestClient, admin_headers: dict[str, str], name: str) -> None:
    item_id = _create(client, admin_headers)
    response = client.put(f"/api/items/{item_id}", headers=admin_headers, json={"name": name})
    assert response.status_code == 422


def test_an_unknown_id_is_404(client: TestClient, admin_headers: dict[str, str]) -> None:
    for response in (
        client.put("/api/items/999", headers=admin_headers, json={"name": "x"}),
        client.delete("/api/items/999", headers=admin_headers),
    ):
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "item_not_found"


def test_writing_needs_the_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.put("/api/items/1", json={"name": "x"}).status_code in (401, 403)
    assert client.delete("/api/items/1").status_code in (401, 403)
