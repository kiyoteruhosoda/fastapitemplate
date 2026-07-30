"""監査イベントの操作対象（何に対しての操作か）。

対象は **種別と内部識別子** で表す。メールアドレス・ユーザー名のような PII は
入れない（ADR-0008）。``user:42`` を後から人が読むには管理画面のユーザー一覧を
突き合わせる。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# DDL と一致させる上限
MAX_TARGET_TYPE_LENGTH = 64
MAX_TARGET_ID_LENGTH = 64


class AuditTargetType(StrEnum):
    """操作対象の種別。値が DB に入る安定キーなので変えない。"""

    USER = "user"
    ROLE = "role"
    PASSKEY = "passkey"
    TWO_FACTOR = "two_factor"
    SYSTEM_SETTINGS = "system_settings"
    SERVICE = "service"


@dataclass(frozen=True)
class AuditTarget:
    """操作対象 1 つ。``identifier`` は内部 ID（``42``）やスコープ名（``web``）。"""

    type: AuditTargetType
    identifier: str | None = None

    @classmethod
    def of(cls, target_type: AuditTargetType, identifier: object = None) -> AuditTarget:
        """識別子を文字列へ揃えて生成する（``int`` の内部 ID をそのまま渡せる）。"""
        return cls(type=target_type, identifier=None if identifier is None else str(identifier))


__all__ = [
    "MAX_TARGET_ID_LENGTH",
    "MAX_TARGET_TYPE_LENGTH",
    "AuditTarget",
    "AuditTargetType",
]
