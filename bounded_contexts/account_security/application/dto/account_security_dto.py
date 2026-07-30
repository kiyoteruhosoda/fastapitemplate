"""ユースケースの入出力（Presentation 層へ返す形）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TwoFactorStatusDto:
    """二要素認証の状態。

    ``enrolling`` は「共有鍵は発行したが、認証アプリでの確認がまだ」の状態。
    """

    enabled: bool
    enrolling: bool


@dataclass(frozen=True)
class TotpEnrollmentDto:
    """登録開始時に利用者へ渡すもの。

    ``secret`` は認証アプリへ QR を読ませられない場合の手入力用。
    """

    secret: str
    otpauth_uri: str


@dataclass(frozen=True)
class PasskeyChallengeDto:
    """ブラウザへ渡す WebAuthn オプションと、検証時に送り返す ID。"""

    challenge_id: str
    public_key: dict[str, Any]


@dataclass(frozen=True)
class PasskeySummaryDto:
    """登録済みパスキーの一覧表示用。"""

    id: int
    name: str
    transports: tuple[str, ...]
    created_at: datetime | None
    last_used_at: datetime | None


__all__ = [
    "PasskeyChallengeDto",
    "PasskeySummaryDto",
    "TotpEnrollmentDto",
    "TwoFactorStatusDto",
]
