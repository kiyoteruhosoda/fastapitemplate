"""IdP が名乗った利用者（クレームを対応付けた結果）。

``subject`` は IdP の中で不変の識別子で、アカウントの結び付けはこれで行う。
メールアドレスは変わり得るため、結び付けの**鍵にはしない**（初回に既存の
ローカルアカウントを見つける手掛かりとしてだけ使う。ADR-0025）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedUser:
    subject: str
    email: str
    username: str
    email_verified: bool = False
    groups: tuple[str, ...] = ()

    @property
    def email_domain(self) -> str:
        _, _, domain = self.email.rpartition("@")
        return domain.lower()


__all__ = ["FederatedUser"]
