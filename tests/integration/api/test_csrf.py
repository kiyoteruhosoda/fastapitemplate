"""Cookie で認証した更新系の CSRF 対策（二重送信トークン。ADR-0028）。

トークンを Cookie へ移すと、ブラウザは**こちらが送るつもりの無いリクエストにも
Cookie を付ける**ようになる。更新系だけ、Cookie とヘッダーの両方に同じ値を求める。
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
    """読み取りの CSRF は結果を攻撃者が読めないので、UI 全体に費用をかけない。"""
    assert client.get("/api/auth/me").status_code == 200


def test_the_entrances_are_exempt(client: TestClient, admin_headers: dict[str, str]) -> None:
    """⚠ ここを塞ぐと、**別のアカウントでログインし直すだけで 403** になる。

    入口はセッションを作る／捨てる操作で、既にあるセッションに対する操作ではない。
    """
    from shared.domain.auth import master_data

    again = client.post(
        "/api/auth/login",
        json={"email": master_data.DEFAULT_ADMIN_EMAIL, "password": master_data.DEFAULT_ADMIN_PASSWORD},
    )
    assert again.status_code == 200
    assert client.post("/api/auth/logout").status_code == 200


def test_a_header_authenticated_caller_does_not_need_it(client: TestClient) -> None:
    """``Authorization`` は自動では送られないので CSRF が成立しない。

    curl・CI・他アプリのために、ヘッダーで来た呼び出しには求めない（ADR-0028 決定 4）。
    """
    # 正規の経路では本文にトークンが載らないので、検証だけを目的に自前で発行する。
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
