"""Scope of a restart.

Vocabulary expressing, per setting, "which service must restart for it to take effect".
Corresponds one-to-one to the application services in ``docker-compose.yml``.

This template has only the ``web`` service. When adding a background worker or the like, add a
value here and call :func:`shared.kernel.restart.start_restart_watcher` in that process's startup.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class RestartScope(StrEnum):
    """Service a restart request is addressed to."""

    WEB = "web"

    @classmethod
    def parse(cls, value: object) -> RestartScope | None:
        """Convert a string to a scope. ``None`` for unknown values."""
        if isinstance(value, RestartScope):
            return value
        if not isinstance(value, str):
            return None
        normalised = value.strip().lower()
        return next((scope for scope in cls if scope.value == normalised), None)

    @classmethod
    def parse_all(cls, values: Iterable[object]) -> tuple[RestartScope, ...]:
        """Convert a sequence of strings to a sequence of scopes (unknown values are dropped).

        The order follows :data:`ALL_RESTART_SCOPES` and duplicates are removed.
        """
        parsed = {scope for scope in (cls.parse(value) for value in values) if scope is not None}
        return tuple(scope for scope in ALL_RESTART_SCOPES if scope in parsed)


ALL_RESTART_SCOPES: tuple[RestartScope, ...] = tuple(RestartScope)


__all__ = ["ALL_RESTART_SCOPES", "RestartScope"]
