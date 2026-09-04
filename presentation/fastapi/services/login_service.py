"""ログインの資格情報検証（パスワード → 二要素認証 → 監査記録）。

ルーターから切り出しているのは、ログインが「入力を受けてトークンを返す」だけの
処理ではないため。実際には照合・第二要素の検証・失敗の理由分けと、そのすべてに
対応する監査記録があり、ルーターに置くと HTTP の関心事に業務の分岐が混ざる。

**応答はどの失敗でも同じ ``invalid_credentials``** に揃える（アカウントの存在を
漏らさないため）。どこで落ちたかは監査ログの ``reason`` にだけ残る。
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.domain.exceptions import (
    InvalidTotpCodeError,
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
from shared.infrastructure.models import User


class LoginService:
    def __init__(self, db: Session, second_factor: VerifySecondFactor, audit: RecordAuditEvent) -> None:
        self._db = db
        self._second_factor = second_factor
        self._audit = audit

    def authenticate(self, credentials: LoginRequest) -> User:
        """資格情報を検証し、通れば利用者を返す。通らなければ 401 を投げる。

        二要素認証が有効なアカウントでは ``totp_code`` も検証する。コード未提示は
        ``totp_required``、不一致は ``invalid_totp`` を返す（どちらもパスワードは
        正しかったことを意味するので、コードを添えて再度ログインすればよい）。
        """
        user = self._db.scalar(select(User).where(User.email == credentials.email))
        if user is None:
            self._reject(None, "unknown_email")
        if not user.is_active:
            self._reject(user, "inactive_user")
        if not check_password_hash(user.password_hash, credentials.password):
            self._reject(user, "invalid_password")

        self._verify_second_factor(user, credentials.totp_code)
        # どの入口で入ったかを残す（ADR-0026 決定 1）。入口ごとに認証の強度が違うため、
        # 記録が無いと「IdP 側で止めたのにまだ入れている」ことに後から気付けない。
        self._audit.as_actor(user.id).execute(AuditEventType.LOGIN_SUCCEEDED, reason="method=password")
        return user

    def _verify_second_factor(self, user: User, totp_code: str | None) -> None:
        try:
            self._second_factor.execute(user_id=user.id, code=totp_code)
        except (TotpRequiredError, InvalidTotpCodeError) as error:
            self._record_failure(user, error.code)
            # 認証の失敗として 401 に揃える（既定の対応付けでは 400 になる）
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": error.code},
            ) from None

    def _reject(self, user: User | None, reason: str) -> NoReturn:
        """失敗を記録し、理由を問わず同じ 401 を返す。

        戻り値を ``NoReturn`` にしているのは、呼び出し側で ``user`` が
        ``User | None`` から ``User`` へ絞り込まれるようにするため。
        """
        self._record_failure(user, reason)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    def _record_failure(self, user: User | None, reason: str) -> None:
        """相手のアカウントは**実行者ではなく対象**として記録する。

        認証に失敗した時点で「誰が試したか」は分かっておらず、実行者に据えると
        アカウントの持ち主が自分でやったように読めてしまう（ADR-0013）。
        """
        self._audit.execute(
            AuditEventType.LOGIN_FAILED,
            AuditResult.FAILURE,
            target=AuditTarget.of(AuditTargetType.USER, user.id) if user is not None else None,
            reason=reason,
        )


__all__ = ["LoginService"]
