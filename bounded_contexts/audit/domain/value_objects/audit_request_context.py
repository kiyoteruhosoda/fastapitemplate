"""Request information attached to audit events.

``request_id`` holds the same value as in the ``log`` table, so "the application logs of one
request" can be matched with "the audit events that happened in that request".
"""

from __future__ import annotations

from dataclasses import dataclass

# Limit matching the DDL (excess is truncated before saving)
MAX_IP_ADDRESS_LENGTH = 45
MAX_USER_AGENT_LENGTH = 512
MAX_REQUEST_ID_LENGTH = 36


@dataclass(frozen=True)
class AuditRequestContext:
    """Client address and tracking key. All ``None`` outside a request (scripts etc.)."""

    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    @classmethod
    def empty(cls) -> AuditRequestContext:
        """Value when there is no request context."""
        return cls()


__all__ = [
    "MAX_IP_ADDRESS_LENGTH",
    "MAX_REQUEST_ID_LENGTH",
    "MAX_USER_AGENT_LENGTH",
    "AuditRequestContext",
]
