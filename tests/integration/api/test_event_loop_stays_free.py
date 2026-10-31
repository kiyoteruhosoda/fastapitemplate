"""DB を使う口と依存関数をイベントループの上で動かさない（ADR-0100）。

``async def`` の中で同期の DB を呼ぶと、後の要求が行のロックを待つあいだ、イベントループごと止まる。先の要求の
確定（``get_db`` の後始末）の順番が回ってこないので、ロック待ちの上限か gunicorn の ``--timeout`` まで固まる
（MariaDB でだけ起きる。SQLite の試験では出ない。task #807）。
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from shared.kernel.database.session import get_db

#: ``async def`` のままにする関数と理由。DB は ``run_in_threadpool`` の中でだけ触る
_STAYS_ASYNC: dict[str, str] = {
    "get_app_or_web_principal": "ログの文脈（ContextVar）を置く。スレッドの中で置くとミドルウェアへ戻らない",
    "receive_backchannel_logout": "本文を await で読む（大きすぎる本文を読まずに断る）",
}


def _own_session(call: Callable[..., object]) -> bool:
    """``get_db`` を通らず、自分でセッションを開く依存関数（失敗の記録を別に確定するものなど）。"""
    return inspect.isfunction(call) and "get_session_factory" in inspect.getsource(call)


def _reaches_db(dependant: Dependant) -> bool:
    if dependant.call is get_db or (dependant.call is not None and _own_session(dependant.call)):
        return True
    return any(_reaches_db(child) for child in dependant.dependencies)


def _coroutines_on_the_way_to_db(dependant: Dependant) -> Iterator[str]:
    if inspect.iscoroutinefunction(dependant.call) and _reaches_db(dependant):
        yield dependant.call.__name__
    for child in dependant.dependencies:
        yield from _coroutines_on_the_way_to_db(child)


def _blocking(app: FastAPI) -> set[str]:
    """DB を使うのに ``async def`` の関数の名前。

    ⚠ **``app.routes`` を直に回さない**（``test_route_authorization.py`` と同じ理由）。
    """
    return {
        name
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
        for name in _coroutines_on_the_way_to_db(context.dependant)
    }


def _an_app_that_blocks() -> FastAPI:
    """規則を破った口を、``include_router`` の奥に置いたアプリ（判定の空振りを見つけるため）。"""

    async def async_dependency(db: object = Depends(get_db)) -> object:
        return db

    def sync_dependency(db: object = Depends(get_db)) -> object:
        return db

    async def free_dependency() -> None: ...

    inner = APIRouter()

    @inner.get("/direct")
    async def async_route(db: object = Depends(get_db)) -> None: ...

    @inner.get("/nested")
    def sync_route_with_async_dependency(db: object = Depends(async_dependency)) -> None: ...

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
        "async_route_through_sync_dependency",
    }


def test_the_real_routes_are_being_looked_at(app: FastAPI) -> None:
    """列挙が空だと、下の試験は素通りする。例外の表の 2 つは必ず見つかるはず。"""
    assert set(_STAYS_ASYNC) <= _blocking(app)


def test_routes_that_use_the_database_do_not_run_on_the_event_loop(app: FastAPI) -> None:
    found = _blocking(app) - set(_STAYS_ASYNC)
    assert not found, f"DB を使うなら def にしてください。await が要るなら DB をスレッドへ逃がして表へ: {found}"
