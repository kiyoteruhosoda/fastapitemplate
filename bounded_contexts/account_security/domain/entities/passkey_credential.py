"""パスキー（WebAuthn 資格情報）。

``sign_count`` は認証器が持つ署名カウンタ。認証のたびに単調増加するため、
巻き戻りは資格情報の複製を疑う手がかりになる。検証そのものは WebAuthn の
ライブラリが行い、ここでは検証済みの新しい値を受け取って進めるだけ。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class PasskeyCredential:
    user_id: int
    credential_id: str
    public_key: str
    sign_count: int = 0
    transports: tuple[str, ...] = ()
    name: str | None = None
    attestation_format: str | None = None
    aaguid: str | None = None
    backup_eligible: bool = False
    backup_state: bool = False
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    # 永続化前は未採番のため None
    id: int | None = None

    def with_usage(self, *, sign_count: int, used_at: datetime) -> PasskeyCredential:
        """認証成功後の状態を返す。"""
        return replace(self, sign_count=sign_count, last_used_at=used_at)

    @property
    def display_name(self) -> str:
        """利用者が識別するための名前（未設定なら資格情報 ID の先頭）。"""
        return self.name or f"passkey-{self.credential_id[:8]}"


__all__ = ["PasskeyCredential"]
