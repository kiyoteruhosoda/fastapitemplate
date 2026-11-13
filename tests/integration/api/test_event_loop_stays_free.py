"""DB-using entrances and dependencies do not run on the event loop (ADR-0100).

Calling a synchronous DB inside ``async def`` freezes the whole event loop while a later request
waits for a row lock. The earlier request never gets its turn to commit (``get_db`` teardown), so it
hangs until the lock-wait limit or gunicorn's ``--timeout`` (only on MariaDB; it does not show in
SQLite tests; task #807).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable, Iterator

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from shared.kernel.database.session import get_db

#: Functions that stay ``async def``, and why. They touch the DB only inside ``run_in_threadpool``
_STAYS_ASYNC: dict[str, str] = {
    "get_app_or_web_principal": "Sets the log context (ContextVar); set in a thread it would not reach the middleware",
    "receive_backchannel_logout": "Reads the body with await (refuses an oversized body without reading it)",
}


def _own_session(call: Callable[..., object]) -> bool:
    """Dependencies that open their own session instead of ``get_db`` (e.g. committing failure records apart)."""
    return inspect.isfunction(call) and "get_session_factory" in inspect.getsource(call)


def _reaches_db(dependant: Dependant) -> bool:
    if dependant.call is get_db or (dependant.call is not None and _own_session(dependant.call)):
        return True
    return any(_reaches_db(child) for child in dependant.dependencies)


def _coroutines_on_the_way_to_db(dependant: Dependant) -> Iterator[str]:
    call = dependant.call
    # For dependencies that ``yield``, ``iscoroutinefunction`` is false
    if (inspect.iscoroutinefunction(call) or inspect.isasyncgenfunction(call)) and _reaches_db(dependant):
        yield call.__name__
    for child in dependant.dependencies:
        yield from _coroutines_on_the_way_to_db(child)


def _blocking(app: FastAPI) -> set[str]:
    """Names of ``async def`` functions that use the DB.

    ⚠ **Do not iterate ``app.routes`` directly** (same reason as ``test_route_authorization.py``).
    """
    return {
        name
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
        for name in _coroutines_on_the_way_to_db(context.dependant)
    }


async def async_dependency(db: object = Depends(get_db)) -> object:
    return db


async def async_yield_dependency(db: object = Depends(get_db)) -> AsyncIterator[object]:
    yield db


def sync_dependency(db: object = Depends(get_db)) -> object:
    return db


async def free_dependency() -> None: ...


def _an_app_that_blocks() -> FastAPI:
    """An app with rule-breaking entrances placed deep inside ``include_router`` (to catch the check missing them)."""
    inner = APIRouter()

    @inner.get("/direct")
    async def async_route(db: object = Depends(get_db)) -> None: ...

    @inner.get("/nested")
    def sync_route_with_async_dependency(db: object = Depends(async_dependency)) -> None: ...

    @inner.get("/yielding")
    def sync_route_with_async_yield_dependency(db: object = Depends(async_yield_dependency)) -> None: ...

    @inner.get("/through")
    async def async_route_through_sync_dependency(db: object = Depends(sync_dependency)) -> None: ...

    @inner.get("/fine")
    def fine(db: object = Depends(sync_dependency), _free: None = Depends(free_dependency)) -> None: ...

    @inner.get("/no-db")
    async def no_db(_free: None = Depends(free_dependency)) -> None: ...

    outer = APIRouter(prefix="/api")
    outer.include_router(inner)
    app = FastAPI()
    app.include_router(outer)
    return app


def test_the_check_catches_a_route_that_breaks_the_rule() -> None:
    assert _blocking(_an_app_that_blocks()) == {
        "async_route",
        "async_dependency",
        "async_yield_dependency",
        "async_route_through_sync_dependency",
    }


def test_the_real_routes_are_being_looked_at(app: FastAPI) -> None:
    """If the listing is empty, the test below passes trivially. The two in the exemption table must always be found."""
    assert set(_STAYS_ASYNC) <= _blocking(app)


def test_routes_that_use_the_database_do_not_run_on_the_event_loop(app: FastAPI) -> None:
    found = _blocking(app) - set(_STAYS_ASYNC)
    assert not found, f"Use def with the DB. If await is needed, move the DB to a thread and list it: {found}"
