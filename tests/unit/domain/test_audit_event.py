"""Audit event enum values and building the operation target.

So stored rows stay readable, ``AuditEventType`` / ``AuditTargetType`` values never change once
used. The values themselves are pinned here to catch accidental renames.
"""

from __future__ import annotations

from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)

# Values whose mismatch with recorded rows would make past audit logs unsearchable
_EXPECTED_EVENT_TYPES = {
    "login.succeeded",
    "login.failed",
    "login.locked",
    "refresh_token.reused",
    "password.changed",
    "password_reset.requested",
    "password_reset.completed",
    "role.switched",
    "sso_login.succeeded",
    "sso_login.failed",
    "sso_user.provisioned",
    "sso_identity.linked",
    "sso_identity.unlinked",
    "two_factor.enabled",
    "two_factor.disabled",
    "passkey.registered",
    "passkey.deleted",
    "user.created",
    "user.updated",
    "user.deleted",
    "role.created",
    "role.updated",
    "role.deleted",
    "system_settings.updated",
    "content_settings.updated",
    "service.restart_requested",
    "profile.updated",
    "group.created",
    "group.updated",
    "group.deleted",
    "notification.sent",
    "tenant.created",
    "tenant.updated",
    "tenant.deleted",
    "tenant.admin_designated",
    "system_admin.added",
    "system_admin.removed",
    "machine_token.issued",
    "machine_token.refused",
    "machine_operation.refused",
    "machine_operation.performed",
}


def test_event_type_values_are_stable() -> None:
    assert {event_type.value for event_type in AuditEventType} == _EXPECTED_EVENT_TYPES


def test_results_are_success_and_failure() -> None:
    assert [result.value for result in AuditResult] == ["success", "failure"]


def test_target_identifier_is_stored_as_text() -> None:
    """Internal IDs can be passed as ``int`` (callers do not have to str() them every time)."""
    target = AuditTarget.of(AuditTargetType.USER, 42)

    assert target.type is AuditTargetType.USER
    assert target.identifier == "42"


def test_target_without_an_identifier() -> None:
    """Operations with "only one target", like a settings change, have no identifier."""
    assert AuditTarget.of(AuditTargetType.SYSTEM_SETTINGS).identifier is None
