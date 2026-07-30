"""WebAuthn チャレンジ（登録・認証の 1 回限りの乱数）。

チャレンジはブラウザへ渡し、署名付きで返ってきたものと一致するかを検証する。
発行したプロセスと検証するプロセスが別になり得る（Gunicorn は複数ワーカーで
動く）ため、プロセスのメモリではなく DB に置く。利用者へは ``challenge_id``
だけを返し、チャレンジそのものは往復させない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# 用途。DB ネイティブ ENUM は使わない方針のため、許可値は Python 側で管理する
# （CLAUDE.md「DB モデリング」参照）。
CHALLENGE_PURPOSE_REGISTRATION = "registration"
CHALLENGE_PURPOSE_AUTHENTICATION = "authentication"
CHALLENGE_PURPOSES: tuple[str, ...] = (
    CHALLENGE_PURPOSE_REGISTRATION,
    CHALLENGE_PURPOSE_AUTHENTICATION,
)


@dataclass(frozen=True)
class WebAuthnChallenge:
    challenge_id: str
    challenge: str
    purpose: str
    expires_at: datetime
    user_id: int | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


__all__ = [
    "CHALLENGE_PURPOSES",
    "CHALLENGE_PURPOSE_AUTHENTICATION",
    "CHALLENGE_PURPOSE_REGISTRATION",
    "WebAuthnChallenge",
]
