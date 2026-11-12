"""Self-restart of the application.

A mechanism that lets administrators order the app itself to restart, to apply settings saved on
the admin screen that **are only read at startup** (logging settings, CORS allowed origins, etc.).

The request is placed in the DB (``app.restart_request`` of ``system_settings``), and each
process picks it up via :class:`RestartWatcher` and terminates itself. The container is restarted
automatically by ``restart: unless-stopped``.

Callers use only this module's public names::

    # Request (admin API)
    RestartRequestStore().save(db, [RestartScope.WEB], requested_by="user:1")

    # Receive (process startup)
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
    """Start watching restart requests addressed to *scope*.

    Does nothing during tests (``TESTING``). If called twice for the same scope, returns the first
    watcher as is (one is expected per Gunicorn worker; avoids duplicates within a process).
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
        # Failing to start the watcher must not stop the app from starting
        logger.warning(
            "Could not start watching restart requests: scope=%s",
            scope.value,
            exc_info=True,
        )
        return None

    _watchers[scope] = watcher
    return watcher


def stop_restart_watchers() -> None:
    """Stop the started watcher threads (on process exit and for test cleanup)."""
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
