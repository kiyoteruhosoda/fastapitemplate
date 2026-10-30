"""認証済み主体（Presentation 層へ渡る検証結果）。

認可の判定は :meth:`can`（scope ベース）のみで行う（CLAUDE.md「権限管理」参照）。

``active_role`` は「いまどのロールで操作しているか」の表示・切り替えのためだけに
持つ（ADR-0078 §1）。**認可の分岐には使わない** — アクティブロールは
:attr:`permissions` を絞り込んだ結果として既に反映されている。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    email: str
    username: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    # None = すべてのロール（保有権限の和集合）で操作している
    active_role: str | None = None
    #: 本人が最後に**実際に**サインインした時刻（UTC・aware。ADR-0076 §10）。更新やロールの
    #: 切り替えでは新しくならない。``None`` は分からない（この仕組みより前のトークン）。
    authenticated_at: datetime | None = None
    #: 所属するテナント（ADR-0079 §1）。``None`` はテナントに属さない（システム管理者）。
    #: ⚠ **``None`` を「全部のテナント」と読まない。** 中身はどのテナントのものも見えない。
    tenant_id: int | None = None
    #: 機械の口から出したトークンなら、名乗った機械の ``client_id``（ADR-0087）。人のログインなら ``None``。
    #: ⚠ 機械の主体は scope で守られた口でしか通らない（:func:`get_current_principal` は断る）。
    machine_client_id: str | None = None

    @property
    def is_machine(self) -> bool:
        return self.machine_client_id is not None

    @property
    def id_hash(self) -> str:
        """ログ用のユーザー識別子（PII を残さないためのハッシュ）。"""
        return hashlib.sha256(str(self.user_id).encode()).hexdigest()[:16]

    def can(self, *codes: str) -> bool:
        """指定された権限コードを **すべて** 保持しているか。"""
        return all(code in self.permissions for code in codes)


__all__ = ["AuthenticatedPrincipal"]
