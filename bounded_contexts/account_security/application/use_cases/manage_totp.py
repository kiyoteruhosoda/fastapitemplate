"""二要素認証（TOTP）の登録・確認・解除。

登録は 2 段階で行う。共有鍵を発行した時点ではまだ有効化せず、利用者が認証
アプリで生成したコードを 1 度検証できてから有効にする。これを 1 段階にすると、
QR の読み取りに失敗した利用者が自分のアカウントから締め出される。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.account_security.application.dto.account_security_dto import (
    TotpEnrollmentDto,
    TwoFactorStatusDto,
)
from bounded_contexts.account_security.domain.entities.totp_secret import TotpSecret
from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
    TotpAlreadyEnabledError,
    TotpNotEnrolledError,
)
from bounded_contexts.account_security.domain.repositories.totp_secret_repository import (
    TotpSecretRepository,
)
from bounded_contexts.account_security.domain.services.totp_authenticator import (
    TotpAuthenticator,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class GetTwoFactorStatus:
    repository: TotpSecretRepository

    def execute(self, user_id: int) -> TwoFactorStatusDto:
        stored = self.repository.find_by_user(user_id)
        if stored is None:
            return TwoFactorStatusDto(enabled=False, enrolling=False)
        return TwoFactorStatusDto(enabled=stored.is_confirmed, enrolling=not stored.is_confirmed)


@dataclass(frozen=True)
class StartTotpEnrollment:
    repository: TotpSecretRepository
    authenticator: TotpAuthenticator

    def execute(self, *, user_id: int, account_name: str) -> TotpEnrollmentDto:
        """共有鍵を発行する（未確認のまま保存）。

        すでに有効な場合は解除してからでないとやり直せない。未確認の登録が
        残っている場合は鍵を作り直す（前回の QR を読めなかった場合の救済）。
        """
        stored = self.repository.find_by_user(user_id)
        if stored is not None and stored.is_confirmed:
            raise TotpAlreadyEnabledError

        secret = self.authenticator.generate_secret()
        self.repository.save(TotpSecret(user_id=user_id, secret=secret))
        return TotpEnrollmentDto(
            secret=secret,
            otpauth_uri=self.authenticator.provisioning_uri(secret=secret, account_name=account_name),
        )


@dataclass(frozen=True)
class ConfirmTotpEnrollment:
    repository: TotpSecretRepository
    authenticator: TotpAuthenticator

    def execute(self, *, user_id: int, code: str) -> None:
        stored = self.repository.find_by_user(user_id)
        if stored is None:
            raise TotpNotEnrolledError
        if stored.is_confirmed:
            raise TotpAlreadyEnabledError
        if not self.authenticator.verify(secret=stored.secret, code=code):
            raise InvalidTotpCodeError
        self.repository.confirm(user_id, utcnow())


@dataclass(frozen=True)
class DisableTotp:
    repository: TotpSecretRepository
    authenticator: TotpAuthenticator

    def execute(self, *, user_id: int, code: str) -> None:
        """二要素認証を解除する。

        解除にも現在のコードを要求する。セッションを乗っ取られただけで
        第二要素まで外せてしまうと、二要素認証の意味が薄れるため。
        """
        stored = self.repository.find_by_user(user_id)
        if stored is None:
            raise TotpNotEnrolledError
        if stored.is_confirmed and not self.authenticator.verify(secret=stored.secret, code=code):
            raise InvalidTotpCodeError
        self.repository.delete(user_id)


__all__ = [
    "ConfirmTotpEnrollment",
    "DisableTotp",
    "GetTwoFactorStatus",
    "StartTotpEnrollment",
]
