from fastapi.testclient import TestClient

from main import create_app


def test_healthcheck() -> None:
    app = create_app(":memory:")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_list_items(tmp_path) -> None:
    db_file = tmp_path / "test.db"
    app = create_app(str(db_file))

    with TestClient(app) as client:
        create_response = client.post("/items", json={"name": "sample"})
        list_response = client.get("/items")

    assert create_response.status_code == 201
    assert create_response.json() == {"id": 1, "name": "sample"}
    assert list_response.status_code == 200
    assert list_response.json() == [{"id": 1, "name": "sample"}]
