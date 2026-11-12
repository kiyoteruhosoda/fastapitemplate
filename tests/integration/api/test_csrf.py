"""CSRF protection for cookie-authenticated writes (double-submit token; ADR-0076 §4).

Once the token moves into a cookie, the browser **attaches the cookie even to requests we never
meant to send**. Only writes require the same value in both the cookie and the header.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from presentation.fastapi.middleware.csrf import CSRF_HEADER, ERROR_CODE


def test_a_state_changing_request_without_the_header_is_refused(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    assert admin_headers[CSRF_HEADER]
    response = client.put("/api/auth/me", json={"email": "x@example.com", "username": "x"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == ERROR_CODE


def test_a_wrong_token_is_refused(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.put(
        "/api/auth/me",
        headers={CSRF_HEADER: "not-the-one"},
        json={"email": "x@example.com", "username": "x"},
    )
    assert response.status_code == 403


def test_reading_never_needs_the_token(client: TestClient, admin_headers: dict[str, str]) -> None:
    """With read CSRF the attacker cannot read the result, so the whole UI does not pay the cost."""
    assert client.get("/api/auth/me").status_code == 200


def test_the_entrances_are_exempt(client: TestClient, admin_headers: dict[str, str]) -> None:
    """⚠ Blocking this would mean **403 just for signing in again with another account**.

    The entrance creates or discards a session; it is not an operation on an existing session.
    """
    from shared.domain.auth import master_data

    again = client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert again.status_code == 200
    assert client.post("/api/auth/logout").status_code == 200


def test_a_header_authenticated_caller_does_not_need_it(client: TestClient) -> None:
    """``Authorization`` is not sent automatically, so CSRF is not possible.

    For curl, CI and other apps, calls that come with the header are not required to have it (ADR-0076 §4 decision 4).
    """
    # The legitimate path never puts the token in the body, so issue one ourselves just for verification.
    from presentation.fastapi.services.token_service import TokenService
    from shared.domain.auth import master_data
    from shared.infrastructure.models import User
    from shared.kernel.database.session import get_db

    session = next(get_db())
    user = session.query(User).filter(User.email == master_data.DEFAULT_ADMIN_EMAIL).one()
    token = str(TokenService.create_token_pair(user)["access_token"])
    session.close()

    client.cookies.clear()
    response = client.put(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "username": "renamed-by-header"},
    )
    assert response.status_code == 200, response.text
