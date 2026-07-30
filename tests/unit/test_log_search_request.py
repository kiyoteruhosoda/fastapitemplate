"""検索条件の正規化（未入力のフォーム項目を「絞り込まない」に丸める）。

画面のフォームは未入力の項目も空文字で送ってくる。空文字をそのまま渡すと
「空文字に一致する行を探せ」になって 0 件になるため、Presentation の
``〇〇Request`` で ``None`` へ丸める（Application 層へはバリデーション済みの値
だけを渡す。CLAUDE.md「API 設計」）。
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
    """0 は「未指定」ではない（真偽で落とすと取りこぼす）。"""
    assert AuditLogSearchRequest(actor_user_id=0).actor_user_id == 0


def test_log_request_upcases_the_level() -> None:
    assert LogSearchRequest(level=" error ").level == "ERROR"


def test_log_request_treats_blank_values_as_unspecified() -> None:
    request = LogSearchRequest(level="", logger="  ", message=" boom ")

    assert request.level is None
    assert request.logger is None
    assert request.message == "boom"


def test_unspecified_paging_is_left_to_the_domain() -> None:
    """既定値・上限の判断は ``LogPage`` が持つ（ここでは素通しする）。"""
    request = LogSearchRequest()

    assert request.limit is None
    assert request.offset is None
