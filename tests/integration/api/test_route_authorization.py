"""Whether every API has authorization (ADR-0089).

Forgetting ``require_permission`` when adding an entrance creates one anyone can call, and tests say nothing.
Public entrances are listed here with a reason.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from bounded_contexts.identity_federation.presentation.app_bearer import get_app_or_web_principal
from presentation.fastapi.dependencies.auth import get_operation_principal, require_any_permission, require_permission

#: Gates that verify the principal. Other dependencies (require_permission, etc.) go through one of them
_GATES: set[Callable[..., object]] = {get_operation_principal, get_app_or_web_principal}

#: Paths that also require a scope (for admin entrances, being signed in is not enough)
_PERMISSION_REQUIRED_PREFIXES = ("/api/admin", "/api/system")

_PUBLIC_ROUTES = {
    # Health checks and build info (exposure is limited by Ingress and nginx)
    ("GET", "/metrics"),
    ("GET", "/api/health"),
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    # Returns only the version. Read by the screen footer and post-deploy checks (ADR-0096)
    ("GET", "/info"),
    # File Android fetches for verification (ADR-0081 §1)
    ("GET", "/.well-known/assetlinks.json"),
    # Default language and theme the screen reads before sign-in (ADR-0080 §1)
    ("GET", "/api/ui/settings"),
    # Entrances before sign-in. Each verifies its own credentials
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/passkey/challenge"),
    ("POST", "/api/auth/passkey/login"),
    # SSO round trip (ADR-0077). The return is checked by state, the exchange by ticket,
    # logout notices by the IdP signature
    ("GET", "/api/auth/sso/provider"),
    ("GET", "/api/auth/sso/login"),
    ("GET", "/api/auth/sso/callback"),
    ("POST", "/api/auth/sso/token"),
    ("GET", "/api/auth/sso/logout"),
    ("GET", "/api/auth/sso/signed-out"),
    ("POST", "/api/auth/sso/backchannel-logout"),
    # Round trip that continues an expired sign-in (ADR-0104). Anyone can start it, but the IdP's
    # prompt=none decides, and the result page returns nothing
    ("GET", "/api/auth/sso/renew"),
    ("GET", "/api/auth/sso/renewed"),
    # Entrance that exchanges machine tokens. Checked by the assay token and the allow list (ADR-0087)
    ("POST", "/api/machine/token"),
}

#: The SPA fallback. Only added when ``frontend/dist`` exists
_PUBLIC_WHEN_BUILT_PATHS = {"/", "/{path:path}"}


def _dependencies(dependant: Dependant) -> Iterator[Callable[..., object]]:
    for child in dependant.dependencies:
        if child.call is not None:
            yield child.call
        yield from _dependencies(child)


def _api_routes(app: FastAPI) -> dict[tuple[str, str], Dependant]:
    """Every API entrance and its effective dependencies.

    ⚠ **Do not iterate ``app.routes`` directly.** Entrances added with ``include_router`` are not listed there
    but wrapped in ``_IncludedRouter`` (iterating it finds none and the test passes). Dependencies from
    ``include_router(dependencies=...)`` exist only in the effective values of ``iter_route_contexts``.
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
    """An app with rule-breaking entrances placed deep inside ``include_router`` (to catch the check missing them)."""
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
    """If the listing is empty, every test below passes trivially (this actually happened on a FastAPI upgrade)."""
    assert {("GET", "/api/auth/me"), ("GET", "/api/admin/users"), ("POST", "/api/auth/login")} <= set(_api_routes(app))


def test_every_route_checks_who_is_calling(app: FastAPI) -> None:
    missing = _unguarded(app)
    assert not missing, f"No authorization. Add require_permission, or if public, list it with a reason: {missing}"


def test_the_public_list_has_no_leftovers(app: FastAPI) -> None:
    """A removed or now-guarded entrance left in the table lets the next one added under that name slip through."""
    routes = _api_routes(app)
    stale = [key for key in _PUBLIC_ROUTES if key not in routes or _GATES & set(_dependencies(routes[key]))]
    assert not stale, f"No longer public entrances; remove them from the table: {stale}"


def test_administration_routes_require_a_permission(app: FastAPI) -> None:
    missing = _administration_without_permission(app)
    assert not missing, f"Admin entrances need a scope: {missing}"


def test_any_permission_is_only_used_for_reading(app: FastAPI) -> None:
    """Using "any one of" for writes makes the audit unable to tell which permission allowed it (ADR-0078 §2)."""
    found = _writes_with_any_permission(app)
    assert not found, f"Use require_permission for writes: {found}"
