"""監査イベント（誰が・いつ・何に対して・何をして・どうなったか）。

PII は持たない。実行者・対象は内部の識別子（サロゲートキー）のみで表す
（ADR-0013）。メールアドレス・ユーザー名・パスワード・トークンは記録しない。
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
    """監査対象の操作。

    値（``<名詞>.<過去形の動詞>``）が DB に入る安定キーなので、一度使った値は
    変えない。新しい操作を監査対象にするときは末尾に追加する。
    """

    # --- 認証 ---
    # ログアウトは記録しない。Cookie を落とすだけの未認証エンドポイントで、
    # 「誰が」を特定できないため（ADR-0013）。
    LOGIN_SUCCEEDED = "login.succeeded"
    LOGIN_FAILED = "login.failed"
    PASSWORD_CHANGED = "password.changed"
    PASSWORD_RESET_REQUESTED = "password_reset.requested"
    PASSWORD_RESET_COMPLETED = "password_reset.completed"
    # --- 二要素認証・パスキー ---
    TWO_FACTOR_ENABLED = "two_factor.enabled"
    TWO_FACTOR_DISABLED = "two_factor.disabled"
    PASSKEY_REGISTERED = "passkey.registered"
    PASSKEY_DELETED = "passkey.deleted"
    # --- ユーザー・ロール管理 ---
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"
    # --- システム運用 ---
    SYSTEM_SETTINGS_UPDATED = "system_settings.updated"
    SERVICE_RESTART_REQUESTED = "service.restart_requested"
    # --- プロフィール（本人によるメールアドレス・表示名の変更。ADR-0016） ---
    PROFILE_UPDATED = "profile.updated"


class AuditResult(StrEnum):
    """操作の成否。失敗だけを追うための絞り込み軸。"""

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class AuditEvent:
    """これから記録する 1 件。

    ``actor_user_id`` は操作した利用者。認証前の失敗（存在しないメールアドレスでの
    ログイン試行）では相手が特定できないため ``None`` になる。
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
    """``audit_log`` から読み出した 1 件（閲覧画面の読み取りモデル）。

    ``event_type`` / ``result`` は保存された文字列をそのまま持つ。過去に使って
    いた値が :class:`AuditEventType` から消えても行は表示できなければならない
    ため、列挙型へ restrict しない。
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
    """検索結果 1 ページと、条件に一致する総件数。"""

    entries: tuple[AuditLogEntry, ...] = field(default_factory=tuple)
    total: int = 0


__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditLogEntry",
    "AuditLogPage",
    "AuditResult",
]
