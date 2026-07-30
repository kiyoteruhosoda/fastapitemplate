"""ログイン時の第二要素検証。

パスワード認証に成功した直後の判定だけを担い、トークン発行には関与しない
（発行は Presentation 層の ``TokenService``）。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
    TotpRequiredError,
)
from bounded_contexts.account_security.domain.repositories.totp_secret_repository import (
    TotpSecretRepository,
)
from bounded_contexts.account_security.domain.services.totp_authenticator import (
    TotpAuthenticator,
)


@dataclass(frozen=True)
class VerifySecondFactor:
    repository: TotpSecretRepository
    authenticator: TotpAuthenticator

    def execute(self, *, user_id: int, code: str | None) -> None:
        """二要素認証が有効なら *code* を検証する。無効なら何もしない。

        未確認の登録（共有鍵は発行済みだが確認していない）は「有効」ではない。
        ここで要求してしまうと、登録を中断した利用者がログインできなくなる。
        """
        stored = self.repository.find_by_user(user_id)
        if stored is None or not stored.is_confirmed:
            return
        if not code:
            raise TotpRequiredError
        if not self.authenticator.verify(secret=stored.secret, code=code):
            raise InvalidTotpCodeError


__all__ = ["VerifySecondFactor"]
