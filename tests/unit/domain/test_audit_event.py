"""監査イベントの列挙値と操作対象の組み立て。

保存済みの行を読めなくしないため、``AuditEventType`` / ``AuditTargetType`` の値は
一度使ったら変えない。ここで値そのものを固定して、うっかりした改名を落とす。
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

# 記録済みの行と対応が崩れると過去の監査ログが引けなくなる値
_EXPECTED_EVENT_TYPES = {
    "login.succeeded",
    "login.failed",
    "password.changed",
    "password_reset.requested",
    "password_reset.completed",
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
    "service.restart_requested",
}


def test_event_type_values_are_stable() -> None:
    assert {event_type.value for event_type in AuditEventType} == _EXPECTED_EVENT_TYPES


def test_results_are_success_and_failure() -> None:
    assert [result.value for result in AuditResult] == ["success", "failure"]


def test_target_identifier_is_stored_as_text() -> None:
    """内部 ID を ``int`` のまま渡せる（呼び出し側で毎回 str() しない）。"""
    target = AuditTarget.of(AuditTargetType.USER, 42)

    assert target.type is AuditTargetType.USER
    assert target.identifier == "42"


def test_target_without_an_identifier() -> None:
    """設定変更のように「対象が 1 つしかない」操作は識別子を持たない。"""
    assert AuditTarget.of(AuditTargetType.SYSTEM_SETTINGS).identifier is None
