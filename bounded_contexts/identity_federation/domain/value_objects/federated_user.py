"""IdP が名乗った利用者（クレームを対応付けた結果）。

``subject`` は IdP の中で不変の識別子で、アカウントの結び付けはこれで行う。
メールアドレスは変わり得るため、結び付けの**鍵にはしない**（初回に既存の
ローカルアカウントを見つける手掛かりとしてだけ使う。ADR-0025）。

⚠ **鍵ではない以上、無くても成立する**（ADR-0042）。IdP によっては出てこない
——**そのときに弾いていたのは、鍵にしていた名残である。**
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedUser:
    subject: str
    #: ⚠ **任意である**（ADR-0042）。結び付けの鍵は ``subject`` なので、既に
    #: 結び付いている相手はメールアドレスが無くても入れる。無いと困るのは
    #: **初回にメールで寄せるとき**と**利用者を作るとき**だけである。
    email: str | None
    username: str
    email_verified: bool = False

    @property
    def email_domain(self) -> str:
        _, _, domain = (self.email or "").rpartition("@")
        return domain.lower()


__all__ = ["FederatedUser"]
