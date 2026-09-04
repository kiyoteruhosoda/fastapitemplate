"""外部 IdP のアカウントと、このアプリの利用者の結び付き。

鍵は ``(issuer, subject)``。メールアドレスは変わり得るので鍵にしない。
1 人の利用者が複数の IdP を持てるよう、利用者側には一意制約を置かない。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedIdentity:
    issuer: str
    subject: str
    user_id: int


__all__ = ["FederatedIdentity"]
