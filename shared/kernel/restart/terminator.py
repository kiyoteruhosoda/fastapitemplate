"""再起動要求を受けたプロセスの終了方法。

コンテナは ``restart: unless-stopped`` で動いているため、「アプリを再起動する」
＝「メインプロセスを綺麗に終わらせる」で足りる。終了後に Docker がコンテナを
起動し直し、entrypoint がマイグレーションから通常どおり走る。

終わらせる相手はプロセス構成によって変わる:

- Gunicorn（本番）: ワーカーではなくアービター（親）を終わらせる。ワーカーだけを
  落としてもアービターが同じ環境で作り直すため、コンテナは再起動しない。
- 単体 Uvicorn（開発）: 監視スレッドが動いているメインプロセス自身。
"""

from __future__ import annotations

import logging
import os
import signal
from typing import Protocol

logger = logging.getLogger(__name__)


class ProcessTerminator(Protocol):
    """再起動のためにプロセスへ終了シグナルを送る。"""

    def terminate(self, reason: str) -> None:
        """graceful shutdown を開始する。"""


class SelfProcessTerminator:
    """自プロセスへ SIGTERM を送る（単体 Uvicorn・ワーカープロセス）。"""

    def terminate(self, reason: str) -> None:
        pid = os.getpid()
        logger.warning(
            "再起動要求により自プロセスを終了します: pid=%s reason=%s",
            pid,
            reason,
            extra={"event": "restart.terminate.self"},
        )
        os.kill(pid, signal.SIGTERM)


class SupervisorProcessTerminator:
    """親プロセス（Gunicorn アービター）へ SIGTERM を送る。"""

    def terminate(self, reason: str) -> None:
        pid = os.getppid()
        logger.warning(
            "再起動要求により親プロセスを終了します: ppid=%s reason=%s",
            pid,
            reason,
            extra={"event": "restart.terminate.supervisor"},
        )
        os.kill(pid, signal.SIGTERM)


def build_process_terminator() -> ProcessTerminator:
    """実行中のプロセス構成に合った終了方法を選ぶ。

    Gunicorn はアービターで ``SERVER_SOFTWARE`` を設定し、ワーカーはそれを
    継承する。この環境変数があるときだけ親（アービター）を終了対象にする。
    """
    if os.environ.get("SERVER_SOFTWARE", "").lower().startswith("gunicorn"):
        return SupervisorProcessTerminator()
    return SelfProcessTerminator()


__all__ = [
    "ProcessTerminator",
    "SelfProcessTerminator",
    "SupervisorProcessTerminator",
    "build_process_terminator",
]
