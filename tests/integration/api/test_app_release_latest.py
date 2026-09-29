"""``GET /api/app-release/latest`` の統合テスト（ADR-0048）。

スマホアプリが開くたびに叩く口。ログインしていれば権限が無くても答えること、
配布面が読めなくても 5xx にしないことを固定する。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from bounded_contexts.app_release.application.latest_app_release import LatestAppReleaseQuery
from bounded_contexts.app_release.domain.app_release import AppRelease, AppReleaseUnavailableError
from bounded_contexts.app_release.presentation.router import get_latest_app_release_query
from tests.conftest import sign_in

_PATH = "/api/app-release/latest"

Answer = AppRelease | Exception | None


class _Source:
    def __init__(self, answer: Answer) -> None:
        self.answer = answer

    def fetch(self) -> AppRelease | None:
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def answer_with(client: TestClient) -> Iterator[Callable[[Answer], None]]:
    """配布面の答えを差し替える（置き場へは行かない）。"""

    def install(answer: Answer) -> None:
        query = LatestAppReleaseQuery(lambda: _Source(answer))
        client.app.dependency_overrides[get_latest_app_release_query] = lambda: query  # type: ignore[attr-defined]

    yield install
    client.app.dependency_overrides.pop(get_latest_app_release_query, None)  # type: ignore[attr-defined]


def test_names_the_latest_release(
    client: TestClient,
    admin_headers: dict[str, str],
    answer_with: Callable[[Answer], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_RELEASE_DOWNLOAD_URL", "https://share.example.test/exampleapp/")
    answer_with(AppRelease(version="1.53.0", build=356, built_at=datetime(2026, 9, 27, 1, 2, 3, tzinfo=UTC)))

    response = client.get(_PATH)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "latest": {
            "version": "1.53.0",
            "build": 356,
            "built_at": "2026-09-27T01:02:03Z",
            "download_url": "https://share.example.test/exampleapp/",
        }
    }


def test_a_person_without_any_permission_is_told_too(
    client: TestClient, admin_headers: dict[str, str], answer_with: Callable[[Answer], None]
) -> None:
    """権限をまだ持たないゲストのアプリにも届ける（権限が付いたとき古い版で取り残されない）。"""
    client.post(
        "/api/admin/users",
        json={"email": "guest@example.com", "username": "guest", "password": "guest-password-1", "roles": []},
        headers=admin_headers,
    )
    client.post("/api/auth/logout", headers=admin_headers)
    sign_in(client, "guest@example.com", "guest-password-1")
    answer_with(AppRelease(version="1.53.0", build=356, built_at=None))

    response = client.get(_PATH)

    assert response.status_code == 200, response.text
    assert response.json()["latest"]["build"] == 356
    assert response.json()["latest"]["built_at"] is None


def test_signing_in_is_required(client: TestClient, answer_with: Callable[[Answer], None]) -> None:
    answer_with(AppRelease(version="1.53.0", build=356, built_at=None))

    assert client.get(_PATH).status_code == 401


def test_an_unreadable_store_is_not_a_server_error(
    client: TestClient, admin_headers: dict[str, str], answer_with: Callable[[Answer], None]
) -> None:
    """配布面の不調で、開いたばかりのアプリにエラーを見せない。"""
    answer_with(AppReleaseUnavailableError("garage is down"))

    response = client.get(_PATH)

    assert response.status_code == 200
    assert response.json() == {"latest": None}


def test_the_default_is_off(client: TestClient, admin_headers: dict[str, str]) -> None:
    """設定が無い既定の状態では置き場へ行かず、何も知らせない。"""
    response = client.get(_PATH)

    assert response.status_code == 200
    assert response.json() == {"latest": None}
