from unittest.mock import patch


def test_shutdown_requires_authentication(client) -> None:
    client.cookies.clear()
    assert client.post("/api/admin/maintenance/shutdown").status_code == 401


def test_shutdown_with_permission(client, admin_headers) -> None:
    with patch("os.kill") as mock_kill:
        response = client.post(
            "/api/admin/maintenance/shutdown", headers=admin_headers
        )
    assert response.status_code == 202
    assert response.json() == {"message": "shutdown initiated"}
    mock_kill.assert_called_once()
