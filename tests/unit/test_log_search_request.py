"""Normalising search conditions (blank form fields become "no filter").

The screen form sends unfilled fields as empty strings. Passing an empty string through would
mean "find rows matching the empty string" and return 0 rows, so the Presentation
``XxxRequest`` rounds them to ``None`` (only validated values are passed to the Application
layer; CLAUDE.md "API design").
"""

from __future__ import annotations

from bounded_contexts.audit.presentation.schemas import (
    AuditLogSearchRequest,
    LogSearchRequest,
)


def test_audit_request_treats_blank_values_as_unspecified() -> None:
    request = AuditLogSearchRequest(event_type="  ", result="", request_id=" req-1 ")

    assert request.event_type is None
    assert request.result is None
    assert request.request_id == "req-1"


def test_audit_request_keeps_a_zero_actor_id() -> None:
    """0 is not "unspecified" (dropping it by truthiness would miss it)."""
    assert AuditLogSearchRequest(actor_user_id=0).actor_user_id == 0


def test_log_request_upcases_the_level() -> None:
    assert LogSearchRequest(level=" error ").level == "ERROR"


def test_log_request_treats_blank_values_as_unspecified() -> None:
    request = LogSearchRequest(level="", logger="  ", message=" boom ")

    assert request.level is None
    assert request.logger is None
    assert request.message == "boom"


def test_unspecified_paging_is_left_to_the_domain() -> None:
    """Defaults and limits are decided by ``LogPage`` (passed through as is here)."""
    request = LogSearchRequest()

    assert request.limit is None
    assert request.offset is None
