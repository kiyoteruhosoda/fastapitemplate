"""パスワードリセット（トークン発行・メール送信・再設定）。

トークンは平文を保存せず SHA-256 ハッシュのみを保存する。
ユーザーの存在有無は API 応答から判別できないようにする（列挙攻撃対策）。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.email_sender.application.send_email import SendEmail
from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.email_sender import (
    EmailSendingDisabledError,
    IEmailSender,
)
from bounded_contexts.email_sender.infrastructure.smtp_email_sender import (
    SmtpEmailSender,
)
from shared.infrastructure.models import PasswordResetToken, User
from shared.infrastructure.models.base import utcnow
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordResetService:
    def __init__(self, sender: IEmailSender | None = None) -> None:
        self._sender = sender or SmtpEmailSender()

    def request_reset(self, session: Session, email: str) -> None:
        """リセットトークンを発行しメールを送る。ユーザー不在でも黙って成功する。"""
        user = session.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active:
            logger.info("password_reset_requested_unknown_email")
            return

        token = secrets.token_urlsafe(32)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_token(token),
                expires_at=utcnow() + timedelta(seconds=settings.password_reset_token_ttl_seconds),
            )
        )
        session.flush()

        base_url = settings.app_base_url.rstrip("/")
        link = f"{base_url}/reset-password?token={token}"
        try:
            SendEmail(self._sender).execute(
                EmailMessage(
                    to=user.email,
                    subject="Password reset",
                    body=(
                        "A password reset was requested for your account.\n"
                        f"Open the following link to set a new password:\n{link}\n\n"
                        "If you did not request this, you can ignore this mail."
                    ),
                )
            )
        except EmailSendingDisabledError:
            logger.warning("password_reset_mail_disabled")

    def reset(self, session: Session, token: str, new_password: str) -> bool:
        """トークンを検証してパスワードを更新する。成功時 True。"""
        from werkzeug.security import generate_password_hash

        row = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(token)))
        if row is None or row.used_at is not None or row.expires_at < utcnow():
            return False
        user = session.get(User, row.user_id)
        if user is None or not user.is_active:
            return False
        user.password_hash = generate_password_hash(new_password)
        row.used_at = utcnow()
        session.flush()
        return True


__all__ = ["PasswordResetService"]
