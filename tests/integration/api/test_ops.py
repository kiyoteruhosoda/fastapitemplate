def test_healthz_ok(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp_utc" in data
    assert isinstance(data["uptime_seconds"], float)


def test_readyz_ok(client) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"] == "ok"
    assert "timestamp_utc" in data


def test_info(client) -> None:
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "git_sha" in data
    assert "build_time" in data
    assert "environment" in data
