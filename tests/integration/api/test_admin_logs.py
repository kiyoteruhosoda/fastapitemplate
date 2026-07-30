import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from shared.infrastructure.models import Log
from shared.infrastructure.models.base import utcnow


def _insert_log(engine: sa.Engine, **overrides: object) -> None:
    session = sessionmaker(bind=engine)()
    defaults = {
        "created_at": utcnow(),
        "level": "INFO",
        "logger": "test",
        "message": "hello",
        "request_id": "req-1",
    }
    session.add(Log(**{**defaults, **overrides}))
    session.commit()
    session.close()


def test_logs_require_permission(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/admin/logs").status_code == 401


def test_list_logs_with_filters(client: TestClient, admin_headers: dict[str, str], engine: sa.Engine) -> None:
    _insert_log(engine, level="INFO", request_id="req-1")
    _insert_log(engine, level="ERROR", request_id="req-2", message="boom")

    response = client.get("/api/admin/logs", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 2

    response = client.get("/api/admin/logs?level=error", headers=admin_headers)
    assert [e["message"] for e in response.json()] == ["boom"]

    response = client.get("/api/admin/logs?request_id=req-1", headers=admin_headers)
    assert {e["request_id"] for e in response.json()} == {"req-1"}
