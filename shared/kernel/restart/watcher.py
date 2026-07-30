"""再起動要求の監視。

各プロセスが自分のスコープ宛の要求を拾い、自分自身を終了させる。復帰は Docker
の restart policy に任せる。

判定は「起動時に読んだ要求の token と現在の token が違うか」で行う。時刻の
大小で判定すると、アプリコンテナと DB の時計がずれている場合に自分が保存した
直後の要求を「まだ未来の要求」と誤認して再起動ループに入り得る。
"""

from __future__ import annotations

import logging
import threading

from shared.kernel.restart.request import (
    RestartRequest,
    RestartRequestReader,
    RestartRequestStore,
)
from shared.kernel.restart.scope import RestartScope
from shared.kernel.restart.terminator import ProcessTerminator, build_process_terminator

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 10.0


class RestartWatcher:
    """再起動要求をポーリングし、対象なら終了シグナルを出す常駐スレッド。"""

    def __init__(
        self,
        scope: RestartScope,
        *,
        store: RestartRequestReader | None = None,
        terminator: ProcessTerminator | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._scope = scope
        self._store = store or RestartRequestStore()
        self._terminator = terminator or build_process_terminator()
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._baseline_token: str | None = None

    @property
    def baseline_token(self) -> str | None:
        """このプロセスが起動時に見た要求の token（比較の基準）。"""
        return self._baseline_token

    def start(self) -> None:
        """基準値を確定させてから監視スレッドを開始する。"""
        if self._thread is not None:
            return
        self._baseline_token = self._current_token()
        self._thread = threading.Thread(
            target=self._run,
            name=f"restart-watcher-{self._scope.value}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "再起動要求の監視を開始しました: scope=%s baseline=%s",
            self._scope.value,
            self._baseline_token or "-",
            extra={"event": "restart.watch.start"},
        )

    def stop(self) -> None:
        self._stop_event.set()

    def should_restart(self, request: RestartRequest | None) -> bool:
        """*request* がこのプロセスの再起動を要求しているか。"""
        if request is None:
            return False
        return request.token != self._baseline_token

    def check_once(self) -> bool:
        """1 回だけ要求を確認し、対象なら終了シグナルを出す。

        戻り値は終了シグナルを出したかどうか。
        """
        request = self._store.load(self._scope)
        if request is None or not self.should_restart(request):
            return False

        self._baseline_token = request.token
        self._terminator.terminate(f"scope={self._scope.value} requested_by={request.requested_by or '-'}")
        return True

    def _current_token(self) -> str | None:
        request = self._store.load(self._scope)
        return request.token if request is not None else None

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval_seconds):
            try:
                if self.check_once():
                    return
            except Exception:
                # DB 一時障害などで監視スレッドを死なせない
                logger.debug("再起動要求の確認に失敗しました", exc_info=True)


__all__ = ["DEFAULT_POLL_INTERVAL_SECONDS", "RestartWatcher"]
