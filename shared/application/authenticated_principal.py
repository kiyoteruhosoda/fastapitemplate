"""認証済み主体（Presentation 層へ渡る検証結果）。

認可の判定は :meth:`can`（scope ベース）のみで行う。ロール名は保持しない
（CLAUDE.md「権限管理」参照）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    email: str
    username: str
    permissions: frozenset[str] = field(default_factory=frozenset)

    @property
    def id_hash(self) -> str:
        """ログ用のユーザー識別子（PII を残さないためのハッシュ）。"""
        return hashlib.sha256(str(self.user_id).encode()).hexdigest()[:16]

    def can(self, *codes: str) -> bool:
        """指定された権限コードを **すべて** 保持しているか。"""
        return all(code in self.permissions for code in codes)


__all__ = ["AuthenticatedPrincipal"]
