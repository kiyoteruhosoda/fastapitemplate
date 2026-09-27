"""ID トークン（および UserInfo）のクレーム -> :class:`FederatedUser` の対応付け。

クレーム名は IdP ごとに違うため設定で変えられる（``OIDC_*_CLAIM``）。ここは
「どの名前から何を読むか」だけを持ち、通信は行わない（純粋な変換なので単体
テストで確かめられる）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bounded_contexts.identity_federation.domain.exceptions import (
    InvalidIdTokenError,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_user import (
    FederatedUser,
)

# 表示名が対応付け先に無いときの代替。IdP の実装差を吸収する。
_USERNAME_FALLBACK_CLAIMS = ("name", "preferred_username", "nickname")


@dataclass(frozen=True)
class ClaimsMapping:
    email_claim: str = "email"
    username_claim: str = "name"

    def apply(self, claims: Mapping[str, Any]) -> FederatedUser:
        """クレームを利用者の情報へ写す。

        ``sub`` が無いものは ID トークンとして成立していない。

        ⚠ **メールアドレスが無くても通す**（ADR-0042）。結び付けの鍵は ``sub`` なので、
        既に結び付いている相手はメールが無くても入れる。**無いと困る場面で断る**
        ——初回にメールで寄せるときと、利用者を作るとき。
        """
        subject = _text(claims.get("sub"))
        if not subject:
            raise InvalidIdTokenError
        email = _text(claims.get(self.email_claim))
        return FederatedUser(
            subject=subject,
            email=email.lower() if email else None,
            username=self._username(claims, email, subject),
            email_verified=claims.get("email_verified") is True,
        )

    def _username(self, claims: Mapping[str, Any], email: str, subject: str) -> str:
        """表示名。対応付け先が空なら別名のクレーム、それも無ければメールの左側。

        ⚠ **メールも無ければ ``sub`` を使う。** 読みにくい値になるが、**表示名が
        空の利用者を作るよりはよい** ——後から画面で直せる。
        """
        candidates = (self.username_claim, *_USERNAME_FALLBACK_CLAIMS)
        for claim in candidates:
            value = _text(claims.get(claim))
            if value:
                return value
        return email.partition("@")[0] if email else subject


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["ClaimsMapping"]
