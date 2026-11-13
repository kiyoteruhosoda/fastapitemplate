"""Watching for restart requests.

Each process picks up requests addressed to its own scope and terminates itself. Coming back is
left to Docker's restart policy.

The decision is "does the current token differ from the one read at startup". Comparing times
could, when the app container's clock and the DB's clock differ, mistake a request saved just
now for "a request still in the future" and fall into a restart loop.
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
    """Resident thread that polls restart requests and sends a termination signal when targeted."""

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
        """Token of the request this process saw at startup (the comparison baseline)."""
        return self._baseline_token

    def start(self) -> None:
        """Fix the baseline, then start the watcher thread."""
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
            "Started watching restart requests: scope=%s baseline=%s",
            self._scope.value,
            self._baseline_token or "-",
            extra={"event": "restart.watch.start"},
        )

    def stop(self) -> None:
        self._stop_event.set()

    def should_restart(self, request: RestartRequest | None) -> bool:
        """Whether *request* asks this process to restart."""
        if request is None:
            return False
        return request.token != self._baseline_token

    def check_once(self) -> bool:
        """Check requests once and send a termination signal if targeted.

        Returns whether a termination signal was sent.
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
                # Do not let a transient DB failure kill the watcher thread
                logger.debug("Failed to check restart requests", exc_info=True)


__all__ = ["DEFAULT_POLL_INTERVAL_SECONDS", "RestartWatcher"]
