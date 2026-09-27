"""外部 IdP のアカウントと、このアプリの利用者の結び付き。

鍵は ``(issuer, subject)``。メールアドレスは変わり得るので鍵にしない。
1 人の利用者が複数の IdP を持てるよう、利用者側には一意制約を置かない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FederatedIdentity:
    issuer: str
    subject: str
    user_id: int
    #: 結び付けた日時。保存されている行を引いたときだけ入る（画面の表示用）。
    linked_at: datetime | None = None
    #: 最後に SSO で入った日時。保存されている行を引いたときだけ入る。
    #: 定期照合が「どのログインに対する失効か」を決める材料になる（ADR-0043）。
    last_login_at: datetime | None = None


__all__ = ["FederatedIdentity"]
