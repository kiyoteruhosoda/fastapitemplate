"""全部の API に認可が掛かっているか（ADR-0089）。

口を足すときに ``require_permission`` を書き忘れると、誰でも叩ける口ができ、試験は何も言わない。
公開する口はここに理由と一緒に書く。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from bounded_contexts.identity_federation.presentation.app_bearer import get_app_or_web_principal
from presentation.fastapi.dependencies.auth import get_operation_principal, require_any_permission, require_permission

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


def _api_routes(app: FastAPI) -> dict[tuple[str, str], Dependant]:
    """全部の API の口と、実効の依存関係。

    ⚠ **``app.routes`` を直に回さない。** ``include_router`` した口はそこに並ばず、``_IncludedRouter`` に
    包まれている（回すと 1 本も見つからないまま試験が通る）。``include_router(dependencies=...)`` の
    依存関係も、``iter_route_contexts`` の実効の値にしか無い。
    """
    routes: dict[tuple[str, str], Dependant] = {}
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, APIRoute) and context.path is not None:
            for method in set(context.methods or ()) - {"HEAD", "OPTIONS"}:
                routes[(method, context.path)] = context.dependant
    return routes


def _permission_factories(dependant: Dependant) -> set[str]:
    names = {call.__qualname__.split(".")[0] for call in _dependencies(dependant) if hasattr(call, "__qualname__")}
    return names & {"require_permission", "require_any_permission"}


def _unguarded(app: FastAPI) -> list[tuple[str, str]]:
    return [
        key
        for key, dependant in _api_routes(app).items()
        if key not in _PUBLIC_ROUTES
        and key[1] not in _PUBLIC_WHEN_BUILT_PATHS
        and not _GATES & set(_dependencies(dependant))
    ]


def _administration_without_permission(app: FastAPI) -> list[tuple[str, str]]:
    return [
        key
        for key, dependant in _api_routes(app).items()
        if key[1].startswith(_PERMISSION_REQUIRED_PREFIXES) and not _permission_factories(dependant)
    ]


def _writes_with_any_permission(app: FastAPI) -> list[tuple[str, str]]:
    return [
        key
        for key, dependant in _api_routes(app).items()
        if key[0] != "GET" and "require_any_permission" in _permission_factories(dependant)
    ]


def _a_badly_guarded_app() -> FastAPI:
    """規則を破った口を、``include_router`` の奥に置いたアプリ（判定の空振りを見つけるため）。"""
    inner = APIRouter(prefix="/admin")

    @inner.get("/open")
    async def forgot_the_guard() -> None: ...

    @inner.get("/signed-in", dependencies=[Depends(get_operation_principal)])
    async def signed_in_only() -> None: ...

    @inner.post("/either", dependencies=[Depends(require_any_permission("a:write", "b:write"))])
    async def writes_with_either() -> None: ...

    @inner.get("/fine", dependencies=[Depends(require_permission("a:view"))])
    async def properly_guarded() -> None: ...

    outer = APIRouter(prefix="/api")
    outer.include_router(inner)
    app = FastAPI()
    app.include_router(outer)
    return app


def test_the_checks_catch_a_route_that_breaks_the_rules() -> None:
    app = _a_badly_guarded_app()
    assert _unguarded(app) == [("GET", "/api/admin/open")]
    assert set(_administration_without_permission(app)) == {("GET", "/api/admin/open"), ("GET", "/api/admin/signed-in")}
    assert _writes_with_any_permission(app) == [("POST", "/api/admin/either")]


def test_the_real_routes_are_being_looked_at(app: FastAPI) -> None:
    """列挙が空だと、下の試験は全部素通りする（FastAPI の版上げで実際に起きた）。"""
    assert {("GET", "/api/auth/me"), ("GET", "/api/admin/users"), ("POST", "/api/auth/login")} <= set(_api_routes(app))


def test_every_route_checks_who_is_calling(app: FastAPI) -> None:
    missing = _unguarded(app)
    assert not missing, f"認可の無い口です。require_permission を付けるか、公開なら理由を書いて表へ: {missing}"


def test_the_public_list_has_no_leftovers(app: FastAPI) -> None:
    """消した口や、認可を付けた口が表に残ると、次に同じ名前で足した口が素通りする。"""
    routes = _api_routes(app)
    stale = [key for key in _PUBLIC_ROUTES if key not in routes or _GATES & set(_dependencies(routes[key]))]
    assert not stale, f"もう公開の口ではありません。表から消してください: {stale}"


def test_administration_routes_require_a_permission(app: FastAPI) -> None:
    missing = _administration_without_permission(app)
    assert not missing, f"管理の口には scope が要ります: {missing}"


def test_any_permission_is_only_used_for_reading(app: FastAPI) -> None:
    """「いずれか 1 つ」を書き込みに使うと、どの権限で許したのか監査から読めない（ADR-0078 §2）。"""
    found = _writes_with_any_permission(app)
    assert not found, f"書き込みには require_permission を使ってください: {found}"
