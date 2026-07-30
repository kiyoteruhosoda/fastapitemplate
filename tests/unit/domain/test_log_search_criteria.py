"""検索条件の正規化（未入力のフォーム項目を「絞り込まない」に丸める）。"""

from __future__ import annotations

from bounded_contexts.audit.domain.value_objects.log_page import LogPage
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    ApplicationLogCriteria,
    AuditLogCriteria,
)


def test_audit_criteria_treats_blank_values_as_unspecified() -> None:
    criteria = AuditLogCriteria.of(event_type="  ", result="", request_id=" req-1 ")

    assert criteria.event_type is None
    assert criteria.result is None
    assert criteria.request_id == "req-1"


def test_audit_criteria_keeps_a_zero_actor_id() -> None:
    """0 は「未指定」ではない（``if actor_user_id`` で落とすと取りこぼす）。"""
    assert AuditLogCriteria.of(actor_user_id=0).actor_user_id == 0


def test_application_criteria_upcases_the_level() -> None:
    assert ApplicationLogCriteria.of(level=" error ").level == "ERROR"


def test_application_criteria_treats_blank_values_as_unspecified() -> None:
    criteria = ApplicationLogCriteria.of(level="", logger_prefix="  ", message_contains=" boom ")

    assert criteria.level is None
    assert criteria.logger_prefix is None
    assert criteria.message_contains == "boom"


def test_criteria_default_to_the_first_page() -> None:
    assert AuditLogCriteria.of().page == LogPage()
    assert ApplicationLogCriteria.of().page == LogPage()
