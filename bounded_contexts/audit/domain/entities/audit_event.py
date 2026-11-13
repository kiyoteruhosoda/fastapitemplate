"""Audit events (who, when, on what, did what, with what outcome).

No PII. The actor and target are represented only by internal identifiers (surrogate keys)
(ADR-0075 §1). Email addresses, user names, passwords and tokens are never recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from bounded_contexts.audit.domain.value_objects.audit_request_context import (
    AuditRequestContext,
)
from bounded_contexts.audit.domain.value_objects.audit_target import AuditTarget


class AuditEventType(StrEnum):
    """Audited operations.

    The value (``<noun>.<past-tense verb>``) is a stable key stored in the DB, so a value once used
    never changes. Append new audited operations at the end.
    """

    # --- Authentication ---
    # Logout is not recorded: it is an unauthenticated endpoint that only drops the cookie, and
    # "who" cannot be identified (ADR-0075 §1).
    LOGIN_SUCCEEDED = "login.succeeded"
    LOGIN_FAILED = "login.failed"
    # Started refusing that account name for a while after repeated failures (ADR-0076 §9)
    LOGIN_LOCKED = "login.locked"
    # A refresh token that was already used came back (suspected theft; ADR-0091)
    REFRESH_TOKEN_REUSED = "refresh_token.reused"
    PASSWORD_CHANGED = "password.changed"
    PASSWORD_RESET_REQUESTED = "password_reset.requested"
    PASSWORD_RESET_COMPLETED = "password_reset.completed"
    # The user switched their own active role (ADR-0078 §1). Recorded so it can later be traced
    # with which permissions they were operating. ``reason`` holds the target role name
    # (role names are not personal information).
    ROLE_SWITCHED = "role.switched"
    # --- SSO (integration with an external IdP; ADR-0077 §1) ---
    # Failures carry no actor (who tried is unknown; ADR-0075 §1).
    SSO_LOGIN_SUCCEEDED = "sso_login.succeeded"
    SSO_LOGIN_FAILED = "sso_login.failed"
    # Created a user from the IdP identity / linked it to an existing user. Both happen only the first time.
    SSO_USER_PROVISIONED = "sso_user.provisioned"
    SSO_IDENTITY_LINKED = "sso_identity.linked"
    # The user linked/unlinked from the settings screen (ADR-0077 §5).
    SSO_IDENTITY_UNLINKED = "sso_identity.unlinked"
    # --- Two-factor authentication, passkeys ---
    TWO_FACTOR_ENABLED = "two_factor.enabled"
    TWO_FACTOR_DISABLED = "two_factor.disabled"
    PASSKEY_REGISTERED = "passkey.registered"
    PASSKEY_DELETED = "passkey.deleted"
    # --- User and role management ---
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"
    # --- System operations ---
    SYSTEM_SETTINGS_UPDATED = "system_settings.updated"
    # --- Content settings (inside a tenant; ADR-0085). ``reason`` holds only the changed item names ---
    CONTENT_SETTINGS_UPDATED = "content_settings.updated"
    SERVICE_RESTART_REQUESTED = "service.restart_requested"
    # --- Profile (the user changing their own email or display name; ADR-0080 §3) ---
    PROFILE_UPDATED = "profile.updated"
    # --- Groups, announcements (ADR-0081 §3) ---
    # A group's ``reason`` holds the member count (listing who joined by ID would get long).
    GROUP_CREATED = "group.created"
    GROUP_UPDATED = "group.updated"
    GROUP_DELETED = "group.deleted"
    # ``reason`` holds the audience, channels and number of recipients (not the body).
    NOTIFICATION_SENT = "notification.sent"
    # Outside the tenants (ADR-0079 §1, §5). Operations by system administrators
    TENANT_CREATED = "tenant.created"
    TENANT_UPDATED = "tenant.updated"
    TENANT_DELETED = "tenant.deleted"
    TENANT_ADMIN_DESIGNATED = "tenant.admin_designated"
    SYSTEM_ADMIN_ADDED = "system_admin.added"
    SYSTEM_ADMIN_REMOVED = "system_admin.removed"
    # --- Machine endpoints (ADR-0087). Actor = the user acted as, target = the machine that identified
    # itself (``machine_client:<client_id>``) ---
    # Records "machine X acting as user Y" (ADR-0082 §1 decision 4). A refusal's ``reason`` is
    # "reason: operation".
    MACHINE_TOKEN_ISSUED = "machine_token.issued"
    MACHINE_TOKEN_REFUSED = "machine_token.refused"
    MACHINE_OPERATION_REFUSED = "machine_operation.refused"
    MACHINE_OPERATION_PERFORMED = "machine_operation.performed"


class AuditResult(StrEnum):
    """Outcome of the operation. A filter axis for tracking failures only."""

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class AuditEvent:
    """One event about to be recorded.

    ``actor_user_id`` is the user who performed the operation. For failures before authentication
    (a sign-in attempt with a nonexistent email) the other party cannot be identified, so it is ``None``.
    """

    event_type: AuditEventType
    result: AuditResult
    occurred_at: datetime
    context: AuditRequestContext
    actor_user_id: int | None = None
    target: AuditTarget | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AuditLogEntry:
    """One entry read from ``audit_log`` (the read model of the viewer screen).

    ``event_type`` / ``result`` keep the stored strings as is. Rows must still be displayable even if
    a previously used value disappears from :class:`AuditEventType`, so they are not restricted to
    the enum.
    """

    id: int
    occurred_at: datetime
    event_type: str
    result: str
    actor_user_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class AuditLogPage:
    """One page of search results and the total count matching the criteria."""

    entries: tuple[AuditLogEntry, ...] = field(default_factory=tuple)
    total: int = 0


__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditLogEntry",
    "AuditLogPage",
    "AuditResult",
]
