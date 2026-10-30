"""ログインの資格情報検証（パスワード → 二要素認証 → 監査記録）。

ルーターから切り出しているのは、ログインが「入力を受けてトークンを返す」だけの
処理ではないため。実際には照合・第二要素の検証・失敗の理由分けと、そのすべてに
対応する監査記録があり、ルーターに置くと HTTP の関心事に業務の分岐が混ざる。

**応答はどの失敗でも同じ ``invalid_credentials``** に揃える（アカウントの存在を
漏らさないため）。どこで落ちたかは監査ログの ``reason`` にだけ残る。
"""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from bounded_contexts.account_security.application.use_cases.throttle_login import ThrottleLogin
from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.domain.entities.login_attempts import PURPOSE_LOGIN
from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
    TooManyAttemptsError,
    TotpRequiredError,
)
from bounded_contexts.audit.application.use_cases.record_audit_event import (
    RecordAuditEvent,
)
from bounded_contexts.audit.domain.entities.audit_event import (
    AuditEventType,
    AuditResult,
)
from bounded_contexts.audit.domain.value_objects.audit_target import (
    AuditTarget,
    AuditTargetType,
)
from presentation.fastapi.schemas.auth import LoginRequest
from shared.domain.auth import master_data
from shared.infrastructure.models import User
from shared.infrastructure.sign_in_directory import account_signing_in
from shared.kernel.settings.secret_guard import PRODUCTION
from shared.kernel.timestamps import utcnow
from shared.kernel.version import load_build_info

#: 未知の宛名でも照合の時間を揃えるためのハッシュ。**何とも一致しない**
#: （応答時間で存在が分かるのを防ぐ。ADR-0076 §9）
_DUMMY_HASH = generate_password_hash("no-account-has-this-password")


@dataclass(frozen=True)
class LoginChecks:
    """資格情報の**前後**に挟む確認。束ねているのは引数の数を設計上の数に収めるため。"""

    second_factor: VerifySecondFactor
    throttle: ThrottleLogin


class LoginService:
    def __init__(self, db: Session, checks: LoginChecks, audit: RecordAuditEvent) -> None:
        self._db = db
        self._second_factor = checks.second_factor
        self._throttle = checks.throttle
        self._audit = audit

    def authenticate(self, credentials: LoginRequest) -> User:
        """資格情報を検証し、通れば利用者を返す。通らなければ 401 を投げる。

        二要素認証が有効なアカウントでは ``totp_code`` も検証する。コード未提示は
        ``totp_required``、不一致は ``invalid_totp`` を返す（どちらもパスワードは
        正しかったことを意味するので、コードを添えて再度ログインすればよい）。

        失敗は宛名ごとに数え、上限に達したらしばらく 429 で断る（ADR-0076 §9）。
        """
        self._require_not_locked(credentials.email)
        user = account_signing_in(self._db, credentials.email, credentials.tenant)
        if user is None:
            # 未知の宛名でも照合の時間を揃える。応答時間で存在が分かるのを防ぐ
            check_password_hash(_DUMMY_HASH, credentials.password)
            self._reject(None, "unknown_email", credentials.email)
        if not user.is_active:
            self._reject(user, "inactive_user", credentials.email)
        if user.password_hash is None:
            # パスワードという入り口を持たない利用者（ADR-0076 §6）。照合する相手が
            # 無いので、ここで断る。
            self._reject(user, "no_local_password", credentials.email)
        if not check_password_hash(user.password_hash, credentials.password):
            self._reject(user, "invalid_password", credentials.email)
        if _is_published_default(credentials.password):
            self._reject(user, "default_password", credentials.email)

        self._verify_second_factor(user, credentials)
        # 正しく入れた。それまでの失敗は打ち間違いなので忘れる
        self._throttle.record_success(PURPOSE_LOGIN, credentials.email)
        # どの入口で入ったかを残す（ADR-0076 §3 決定 1）。入口ごとに認証の強度が違うため、
        # 記録が無いと「IdP 側で止めたのにまだ入れている」ことに後から気付けない。
        self._audit.as_actor(user.id).execute(AuditEventType.LOGIN_SUCCEEDED, reason="method=password")
        return user

    def _require_not_locked(self, identifier: str) -> None:
        """断っている最中なら、照合の前に 429（ADR-0076 §9）。

        断られた試行も監査に残す ——当たられていることは、断っているあいだにこそ見える。
        誰のアカウントかはまだ引いていないので対象は空。
        """
        try:
            self._throttle.require_allowed(PURPOSE_LOGIN, identifier, utcnow())
        except TooManyAttemptsError:
            self._audit.execute(AuditEventType.LOGIN_FAILED, AuditResult.FAILURE, reason="locked")
            raise

    def _verify_second_factor(self, user: User, credentials: LoginRequest) -> None:
        """二要素のコードを確かめる。**間違いもパスワードと同じ数え上げに入れる**（ADR-0076 §9）。"""
        try:
            self._second_factor.execute(user_id=user.id, code=credentials.totp_code)
        except (TotpRequiredError, InvalidTotpCodeError) as error:
            self._record_failure(user, error.code, credentials.email)
            # 認証の失敗として 401 に揃える（既定の対応付けでは 400 になる）
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": error.code},
            ) from None

    def _reject(self, user: User | None, reason: str, identifier: str) -> NoReturn:
        """失敗を記録し、理由を問わず同じ 401 を返す。

        戻り値を ``NoReturn`` にしているのは、呼び出し側で ``user`` が
        ``User | None`` から ``User`` へ絞り込まれるようにするため。
        """
        self._record_failure(user, reason, identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    def _record_failure(self, user: User | None, reason: str, identifier: str) -> None:
        """相手のアカウントは**実行者ではなく対象**として記録する。

        認証に失敗した時点で「誰が試したか」は分かっておらず、実行者に据えると
        アカウントの持ち主が自分でやったように読めてしまう（ADR-0075 §1）。

        失敗は宛名ごとに数え、上限に達したら断り始めたことも残す（ADR-0076 §9）。
        """
        target = AuditTarget.of(AuditTargetType.USER, user.id) if user is not None else None
        self._audit.execute(AuditEventType.LOGIN_FAILED, AuditResult.FAILURE, target=target, reason=reason)
        if self._throttle.record_attempt(PURPOSE_LOGIN, identifier, utcnow()):
            self._audit.execute(AuditEventType.LOGIN_LOCKED, AuditResult.FAILURE, target=target, reason=reason)


def _is_published_default(password: str) -> bool:
    """本番で、公開されている既定のパスワードで入ろうとしているか（ADR-0073 §4）。

    既定の管理者は ``ADMIN_INITIAL_PASSWORD`` を渡し忘れると、リポジトリに載っている
    パスワードのまま全権で据わる。**本番ではその値では入れない**ようにして、渡し忘れを
    「誰でも入れる」ではなく「誰も入れない」に倒す。開発では今までどおり入れる。
    """
    if load_build_info().environment != PRODUCTION:
        return False
    return compare_digest(password.encode(), master_data.DEFAULT_ADMIN_PASSWORD.encode())


__all__ = ["LoginChecks", "LoginService"]
