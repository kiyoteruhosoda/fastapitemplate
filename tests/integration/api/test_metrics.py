def test_metrics_endpoint_available(client) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_metrics_contains_http_duration_histogram(client) -> None:
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    # Histogram is always emitted once any request is instrumented
    assert "http_request_duration_seconds" in response.text
