"""アプリケーションの自己再起動。

管理画面で保存した設定のうち、**起動時にしか読まれないもの**（ログ設定・CORS
の許可オリジン等）を反映するために、管理者がアプリ自身から再起動を指示できる
ようにする仕組み。

要求は DB（``system_settings`` の ``app.restart_request``）に置き、各プロセスが
:class:`RestartWatcher` で拾って自分を終了させる。コンテナは
``restart: unless-stopped`` で自動的に起動し直される。

呼び出し側はこのモジュールの公開名だけを使う::

    # 要求する（管理 API）
    RestartRequestStore().save(db, [RestartScope.WEB], requested_by="user:1")

    # 受け取る（プロセスの起動処理）
    start_restart_watcher(RestartScope.WEB)
"""

from __future__ import annotations

import logging

from shared.kernel.restart.request import (
    RESTART_REQUEST_SETTING_KEY,
    RestartRequest,
    RestartRequestReader,
    RestartRequestStore,
)
from shared.kernel.restart.scope import ALL_RESTART_SCOPES, RestartScope
from shared.kernel.restart.terminator import (
    ProcessTerminator,
    SelfProcessTerminator,
    SupervisorProcessTerminator,
    build_process_terminator,
)
from shared.kernel.restart.watcher import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    RestartWatcher,
)

logger = logging.getLogger(__name__)

_watchers: dict[RestartScope, RestartWatcher] = {}


def start_restart_watcher(scope: RestartScope) -> RestartWatcher | None:
    """*scope* 宛の再起動要求の監視を開始する。

    テスト実行時（``TESTING``）は何もしない。同じスコープで二重に呼ばれた場合は
    最初のウォッチャーをそのまま返す（Gunicorn ワーカーごとに 1 つ動く想定で、
    プロセス内で重複しないようにする）。
    """
    from shared.kernel.settings.settings import settings

    if settings.testing:
        return None

    existing = _watchers.get(scope)
    if existing is not None:
        return existing

    watcher = RestartWatcher(scope)
    try:
        watcher.start()
    except Exception:
        # 監視が立ち上がらないこと自体でアプリ起動を止めない
        logger.warning(
            "再起動要求の監視を開始できませんでした: scope=%s",
            scope.value,
            exc_info=True,
        )
        return None

    _watchers[scope] = watcher
    return watcher


def stop_restart_watchers() -> None:
    """起動済みの監視スレッドを止める（プロセス終了時・テスト後始末用）。"""
    for watcher in _watchers.values():
        watcher.stop()
    _watchers.clear()


__all__ = [
    "ALL_RESTART_SCOPES",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "RESTART_REQUEST_SETTING_KEY",
    "ProcessTerminator",
    "RestartRequest",
    "RestartRequestReader",
    "RestartRequestStore",
    "RestartScope",
    "RestartWatcher",
    "SelfProcessTerminator",
    "SupervisorProcessTerminator",
    "build_process_terminator",
    "start_restart_watcher",
    "stop_restart_watchers",
]
