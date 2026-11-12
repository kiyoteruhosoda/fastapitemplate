"""Target of an audit event (what the operation was performed on).

Targets are represented by **type and internal identifier**. No PII such as email addresses or user
names (ADR-0075 §1). For a person to read ``user:42`` later, match it against the user list on the
admin screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Limit matching the DDL
MAX_TARGET_TYPE_LENGTH = 64
MAX_TARGET_ID_LENGTH = 64


class AuditTargetType(StrEnum):
    """Type of the target. The value is a stable key stored in the DB, so never change it."""

    USER = "user"
    ROLE = "role"
    PASSKEY = "passkey"
    TWO_FACTOR = "two_factor"
    SYSTEM_SETTINGS = "system_settings"
    CONTENT_SETTINGS = "content_settings"
    SERVICE = "service"
    GROUP = "group"
    NOTIFICATION = "notification"
    TENANT = "tenant"
    MACHINE_CLIENT = "machine_client"


@dataclass(frozen=True)
class AuditTarget:
    """One target. ``identifier`` is an internal ID (``42``) or a scope name (``web``)."""

    type: AuditTargetType
    identifier: str | None = None

    @classmethod
    def of(cls, target_type: AuditTargetType, identifier: object = None) -> AuditTarget:
        """Create it with the identifier normalized to a string (an ``int`` internal ID can be passed as is)."""
        return cls(type=target_type, identifier=None if identifier is None else str(identifier))


__all__ = [
    "MAX_TARGET_ID_LENGTH",
    "MAX_TARGET_TYPE_LENGTH",
    "AuditTarget",
    "AuditTargetType",
]
