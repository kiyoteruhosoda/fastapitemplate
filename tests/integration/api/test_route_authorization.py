"""全部の API に認可が掛かっているか（ADR-0089）。

口を足すときに ``require_permission`` を書き忘れると、誰でも叩ける口ができ、試験は何も言わない。
公開する口はここに理由と一緒に書く。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from bounded_contexts.identity_federation.presentation.app_bearer import get_app_or_web_principal
from presentation.fastapi.dependencies.auth import get_operation_principal

#: 主体を確かめる関門。ほかの依存関数（require_permission など）はどれかを通る
_GATES: set[Callable[..., object]] = {get_operation_principal, get_app_or_web_principal}

#: scope まで求める経路（管理の口は、入っているだけでは足りない）
_PERMISSION_REQUIRED_PREFIXES = ("/api/admin", "/api/system")

_PUBLIC_ROUTES = {
    # 稼働の確かめ・ビルド情報（公開の範囲は Ingress と nginx で絞る）
    ("GET", "/metrics"),
    ("GET", "/api/health"),
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("GET", "/info"),
    # Android が確かめに来るファイル（ADR-0081 §1）
    ("GET", "/.well-known/assetlinks.json"),
    # ログインの前に画面が読む既定の言語とテーマ（ADR-0080 §1）
    ("GET", "/api/ui/settings"),
    # 入る前の口。それぞれ自分で資格情報を確かめる
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/passkey/challenge"),
    ("POST", "/api/auth/passkey/login"),
    # SSO の往復（ADR-0077）。戻りは state、引き換えは券、停止の通知は IdP の署名で確かめる
    ("GET", "/api/auth/sso/provider"),
    ("GET", "/api/auth/sso/login"),
    ("GET", "/api/auth/sso/callback"),
    ("POST", "/api/auth/sso/token"),
    ("GET", "/api/auth/sso/logout"),
    ("GET", "/api/auth/sso/signed-out"),
    ("POST", "/api/auth/sso/backchannel-logout"),
    # 機械のトークンを換える口。assay のトークンと許可簿で確かめる（ADR-0087）
    ("POST", "/api/machine/token"),
}

#: 画面（SPA）の受け皿。``frontend/dist`` があるときだけ足される
_PUBLIC_WHEN_BUILT_PATHS = {"/", "/{path:path}"}


def _dependencies(dependant: Dependant) -> Iterator[Callable[..., object]]:
    for child in dependant.dependencies:
        if child.call is not None:
            yield child.call
        yield from _dependencies(child)


def _api_routes(app: FastAPI) -> Iterator[tuple[str, str, APIRoute]]:
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, route.path, route


def _permission_factories(route: APIRoute) -> set[str]:
    names = {
        call.__qualname__.split(".")[0] for call in _dependencies(route.dependant) if hasattr(call, "__qualname__")
    }
    return names & {"require_permission", "require_any_permission"}


def test_every_route_checks_who_is_calling(app: FastAPI) -> None:
    missing = [
        (method, path)
        for method, path, route in _api_routes(app)
        if (method, path) not in _PUBLIC_ROUTES
        and path not in _PUBLIC_WHEN_BUILT_PATHS
        and not _GATES & set(_dependencies(route.dependant))
    ]
    assert not missing, f"認可の無い口です。require_permission を付けるか、公開なら理由を書いて表へ: {missing}"


def test_the_public_list_has_no_leftovers(app: FastAPI) -> None:
    """消した口や、認可を付けた口が表に残ると、次に同じ名前で足した口が素通りする。"""
    routes = {(method, path): route for method, path, route in _api_routes(app)}
    stale = [key for key in _PUBLIC_ROUTES if key not in routes or _GATES & set(_dependencies(routes[key].dependant))]
    assert not stale, f"もう公開の口ではありません。表から消してください: {stale}"


def test_administration_routes_require_a_permission(app: FastAPI) -> None:
    missing = [
        (method, path)
        for method, path, route in _api_routes(app)
        if path.startswith(_PERMISSION_REQUIRED_PREFIXES) and not _permission_factories(route)
    ]
    assert not missing, f"管理の口には scope が要ります: {missing}"


def test_any_permission_is_only_used_for_reading(app: FastAPI) -> None:
    """「いずれか 1 つ」を書き込みに使うと、どの権限で許したのか監査から読めない（ADR-0078 §2）。"""
    found = [
        (method, path)
        for method, path, route in _api_routes(app)
        if method != "GET" and "require_any_permission" in _permission_factories(route)
    ]
    assert not found, f"書き込みには require_permission を使ってください: {found}"
