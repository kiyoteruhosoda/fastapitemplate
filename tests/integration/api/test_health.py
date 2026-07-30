from fastapi.testclient import TestClient


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_response_has_request_id_header(client: TestClient) -> None:
    response = client.get("/api/health")
    assert "x-request-id" in response.headers


def test_healthz_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert isinstance(data["uptime_seconds"], float)


def test_readyz_ok(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"


def test_info(client: TestClient) -> None:
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert {"version", "git_sha", "branch", "build_time", "environment"} <= set(data)


def test_metrics_endpoint_available(client: TestClient) -> None:
    client.get("/api/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_request" in response.text
