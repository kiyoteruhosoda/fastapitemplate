"""ユースケースの組み立て（``Depends()`` 用のファクトリ）。

依存の生成をここへ集約し、ルーターは完成したユースケースだけを受け取る
（CLAUDE.md「設計方針」の依存注入）。設定値は ``settings`` の ``@property``
経由でのみ読む。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from bounded_contexts.account_security.application.use_cases.authenticate_with_passkey import (
    CompletePasskeyAuthentication,
    StartPasskeyAuthentication,
)
from bounded_contexts.account_security.application.use_cases.manage_passkeys import (
    DeletePasskey,
    ListPasskeys,
)
from bounded_contexts.account_security.application.use_cases.manage_totp import (
    ConfirmTotpEnrollment,
    DisableTotp,
    GetTwoFactorStatus,
    StartTotpEnrollment,
)
from bounded_contexts.account_security.application.use_cases.register_passkey import (
    CompletePasskeyRegistration,
    StartPasskeyRegistration,
)
from bounded_contexts.account_security.application.use_cases.throttle_login import ThrottleLogin
from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.domain.entities.login_attempts import ThrottlePolicy
from bounded_contexts.account_security.domain.services.totp_authenticator import (
    TotpAuthenticator,
)
from bounded_contexts.account_security.domain.services.webauthn_relying_party import (
    WebAuthnRelyingParty,
)
from bounded_contexts.account_security.infrastructure.py_webauthn_relying_party import (
    PyWebAuthnRelyingParty,
)
from bounded_contexts.account_security.infrastructure.pyotp_totp_authenticator import (
    PyotpTotpAuthenticator,
)
from bounded_contexts.account_security.infrastructure.sql_login_attempt_repository import (
    SqlLoginAttemptRepository,
)
from bounded_contexts.account_security.infrastructure.sql_passkey_credential_repository import (
    SqlPasskeyCredentialRepository,
)
from bounded_contexts.account_security.infrastructure.sql_totp_secret_repository import (
    SqlTotpSecretRepository,
)
from bounded_contexts.account_security.infrastructure.sql_webauthn_challenge_repository import (
    SqlWebAuthnChallengeRepository,
)
from shared.kernel.database.db import get_session_factory
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings

DbDep = Annotated[Session, Depends(get_db)]


def build_totp_authenticator() -> TotpAuthenticator:
    return PyotpTotpAuthenticator(issuer=settings.totp_issuer, valid_window=settings.totp_valid_window)


def build_relying_party() -> WebAuthnRelyingParty:
    return PyWebAuthnRelyingParty(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        origin=settings.webauthn_origin,
    )


# 外部要素（TOTP 実装・WebAuthn ライブラリ）は依存として差し込む。テストでは
# ``app.dependency_overrides`` で偽物へ差し替えられる。
TotpAuthenticatorDep = Annotated[TotpAuthenticator, Depends(build_totp_authenticator)]
RelyingPartyDep = Annotated[WebAuthnRelyingParty, Depends(build_relying_party)]


# --- TOTP ---------------------------------------------------------------


def get_two_factor_status(db: DbDep) -> GetTwoFactorStatus:
    return GetTwoFactorStatus(repository=SqlTotpSecretRepository(db))


def start_totp_enrollment(db: DbDep, authenticator: TotpAuthenticatorDep) -> StartTotpEnrollment:
    return StartTotpEnrollment(repository=SqlTotpSecretRepository(db), authenticator=authenticator)


def confirm_totp_enrollment(db: DbDep, authenticator: TotpAuthenticatorDep) -> ConfirmTotpEnrollment:
    return ConfirmTotpEnrollment(repository=SqlTotpSecretRepository(db), authenticator=authenticator)


def disable_totp(db: DbDep, authenticator: TotpAuthenticatorDep) -> DisableTotp:
    return DisableTotp(repository=SqlTotpSecretRepository(db), authenticator=authenticator)


def verify_second_factor(db: DbDep, authenticator: TotpAuthenticatorDep) -> VerifySecondFactor:
    return VerifySecondFactor(repository=SqlTotpSecretRepository(db), authenticator=authenticator)


def throttle_policy() -> ThrottlePolicy:
    """窓・上限・断る長さ。**設定は呼ばれるたびに読む**（再起動を要らなくする）。"""
    return ThrottlePolicy(
        max_failures=settings.login_max_failures,
        window=timedelta(seconds=settings.login_failure_window_seconds),
        lock_duration=timedelta(seconds=settings.login_lock_seconds),
    )


def throttle_login() -> ThrottleLogin:
    # ⚠ リクエストのセッションは渡さない。失敗の記録は 401 と一緒に返る（例外で
    # 抜ける）ので、リクエストのセッションでは rollback で消える。控えは自前の
    # 短いセッションで commit する（ADR-0076 §9）
    return ThrottleLogin(SqlLoginAttemptRepository(get_session_factory()), throttle_policy())


# --- パスキー -----------------------------------------------------------


def list_passkeys(db: DbDep) -> ListPasskeys:
    return ListPasskeys(repository=SqlPasskeyCredentialRepository(db))


def delete_passkey(db: DbDep) -> DeletePasskey:
    return DeletePasskey(repository=SqlPasskeyCredentialRepository(db))


def start_passkey_registration(db: DbDep, relying_party: RelyingPartyDep) -> StartPasskeyRegistration:
    return StartPasskeyRegistration(
        credentials=SqlPasskeyCredentialRepository(db),
        challenges=SqlWebAuthnChallengeRepository(db),
        relying_party=relying_party,
        challenge_ttl_seconds=settings.webauthn_challenge_ttl_seconds,
    )


def complete_passkey_registration(db: DbDep, relying_party: RelyingPartyDep) -> CompletePasskeyRegistration:
    return CompletePasskeyRegistration(
        credentials=SqlPasskeyCredentialRepository(db),
        challenges=SqlWebAuthnChallengeRepository(db),
        relying_party=relying_party,
    )


def start_passkey_authentication(db: DbDep, relying_party: RelyingPartyDep) -> StartPasskeyAuthentication:
    return StartPasskeyAuthentication(
        challenges=SqlWebAuthnChallengeRepository(db),
        relying_party=relying_party,
        challenge_ttl_seconds=settings.webauthn_challenge_ttl_seconds,
    )


def complete_passkey_authentication(db: DbDep, relying_party: RelyingPartyDep) -> CompletePasskeyAuthentication:
    return CompletePasskeyAuthentication(
        credentials=SqlPasskeyCredentialRepository(db),
        challenges=SqlWebAuthnChallengeRepository(db),
        relying_party=relying_party,
    )


__all__ = [
    "RelyingPartyDep",
    "TotpAuthenticatorDep",
    "build_relying_party",
    "build_totp_authenticator",
    "complete_passkey_authentication",
    "complete_passkey_registration",
    "confirm_totp_enrollment",
    "delete_passkey",
    "disable_totp",
    "get_two_factor_status",
    "list_passkeys",
    "start_passkey_authentication",
    "start_passkey_registration",
    "start_totp_enrollment",
    "throttle_login",
    "throttle_policy",
    "verify_second_factor",
]
