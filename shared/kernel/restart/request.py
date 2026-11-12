"""Persistence of restart requests.

The ``app.restart_request`` record of the ``system_settings`` table is the single source that
holds "when, who, and which service's restart was requested".

The admin API process cannot signal the process to be restarted directly (Gunicorn runs several
workers, and if services are split in the future they become separate containers). The request
is placed in the DB; each process picks it up via :mod:`shared.kernel.restart.watcher`,
terminates itself, and comes back through Docker's restart policy. This way the Docker socket
does not have to be mounted into the container.

Requests are held **independently per scope**. With a single overwritten request, if two
requests arrive within the watcher's polling interval (default 10 seconds), the later one
overwrites the earlier before it is read, and a process that has not read it yet misses the
restart meant for it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from shared.kernel.restart.scope import ALL_RESTART_SCOPES, RestartScope
from shared.kernel.timestamps import utcnow_aware

logger = logging.getLogger(__name__)

RESTART_REQUEST_SETTING_KEY = "app.restart_request"


@dataclass(frozen=True)
class RestartRequest:
    """The latest restart request for a scope.

    ``token`` identifies the request (the ISO form of the request time). The watcher takes the
    token read at startup as its baseline and restarts only when the value **changes**. Because
    it compares for change rather than ordering of times, it does not fall into a restart loop
    even if the app container's clock and the DB's clock differ.
    """

    scope: RestartScope
    token: str
    requested_at: datetime | None
    requested_by: str | None
    reason: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "requested_by": self.requested_by,
            "reason": self.reason,
        }

    @classmethod
    def from_payload(cls, scope: RestartScope, payload: Any) -> RestartRequest | None:
        if not isinstance(payload, dict):
            return None
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            return None
        requested_by = payload.get("requested_by")
        reason = payload.get("reason")
        return cls(
            scope=scope,
            token=token,
            requested_at=_parse_timestamp(payload.get("requested_at")),
            requested_by=requested_by if isinstance(requested_by, str) else None,
            reason=reason if isinstance(reason, str) else None,
        )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _decode_requests(payload: Any) -> dict[RestartScope, RestartRequest]:
    """Decode the stored form ``{"scopes": {"web": {...}}}``."""
    if not isinstance(payload, dict):
        return {}
    raw_scopes = payload.get("scopes")
    if not isinstance(raw_scopes, dict):
        return {}

    requests: dict[RestartScope, RestartRequest] = {}
    for raw_scope, raw_request in raw_scopes.items():
        scope = RestartScope.parse(raw_scope)
        if scope is None:
            continue
        request = RestartRequest.from_payload(scope, raw_request)
        if request is not None:
            requests[scope] = request
    return requests


def _encode_requests(requests: Mapping[RestartScope, RestartRequest]) -> dict[str, Any]:
    return {"scopes": {scope.value: requests[scope].to_payload() for scope in ALL_RESTART_SCOPES if scope in requests}}


class RestartRequestReader(Protocol):
    """Read the restart request addressed to a scope.

    :class:`~shared.kernel.restart.watcher.RestartWatcher` depends only on this interface
    (DIP), so a test double without a DB can be substituted.
    """

    def load(self, scope: RestartScope) -> RestartRequest | None:
        """Return the latest request for *scope*, or ``None`` if there is none."""


class RestartRequestStore:
    """Reads and writes the ``app.restart_request`` record."""

    def load_all(self) -> dict[RestartScope, RestartRequest]:
        """Return the latest request per scope. Empty when the DB is unavailable."""
        from shared.kernel.settings.system_setting_records import (
            SystemSettingRecordReader,
        )

        try:
            payload = SystemSettingRecordReader.read_json(RESTART_REQUEST_SETTING_KEY)
        except Exception:
            logger.debug("Failed to read restart requests", exc_info=True)
            return {}
        return _decode_requests(payload)

    def load(self, scope: RestartScope) -> RestartRequest | None:
        """Return the latest request for *scope*."""
        return self.load_all().get(scope)

    def save(
        self,
        session: Session,
        scopes: Iterable[RestartScope],
        *,
        requested_by: str | None = None,
        reason: str | None = None,
    ) -> tuple[RestartRequest, ...]:
        """Save a restart request (call from within a request).

        If no targets are given, all scopes are targeted. Only the given scopes are rewritten;
        requests left for other scopes are kept (so requests not yet picked up are not lost).

        The request time is always taken here. To pin it in tests, patch
        :func:`datetime.datetime.now` (see "Tests" in CLAUDE.md).
        """
        from shared.infrastructure.models import SystemSetting

        targets = tuple(scope for scope in ALL_RESTART_SCOPES if scope in set(scopes))
        if not targets:
            targets = ALL_RESTART_SCOPES

        moment = utcnow_aware()
        token = moment.isoformat()

        record = session.get(SystemSetting, RESTART_REQUEST_SETTING_KEY)
        requests = _decode_requests(record.setting_json if record is not None else None)
        for scope in targets:
            requests[scope] = RestartRequest(
                scope=scope,
                token=token,
                requested_at=moment,
                requested_by=requested_by,
                reason=reason,
            )

        payload = _encode_requests(requests)
        if record is None:
            session.add(SystemSetting(setting_key=RESTART_REQUEST_SETTING_KEY, setting_json=payload))
        else:
            record.setting_json = payload
        session.flush()

        logger.info(
            "Saved restart request: scopes=%s requested_by=%s",
            ",".join(scope.value for scope in targets),
            requested_by or "-",
            extra={"event": "restart.requested"},
        )
        return tuple(requests[scope] for scope in targets)


__all__ = [
    "RESTART_REQUEST_SETTING_KEY",
    "RestartRequest",
    "RestartRequestReader",
    "RestartRequestStore",
]
