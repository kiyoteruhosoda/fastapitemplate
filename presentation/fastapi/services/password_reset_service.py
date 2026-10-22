"""パスワードリセット（トークン発行・メール送信・再設定）。

トークンは平文を保存せず SHA-256 ハッシュのみを保存する。
ユーザーの存在有無は API 応答から判別できないようにする（列挙攻撃対策）。

⚠ **パスワードを持たない利用者には発行しない**（ADR-0038）。リセットを通すと、
「この利用者は SSO でしか入れない」が黙って崩れる。応答は不在のときと同じ。
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
from shared.infrastructure.sign_in_directory import account_signing_in
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

INVITATION = "invitation"
#: 招待の有効期限。⚠ 設定にしない（運用で決め直す値ではない）。
INVITATION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordResetService:
    def __init__(self, sender: IEmailSender | None = None) -> None:
        self._sender = sender or SmtpEmailSender()

    def request_reset(self, session: Session, email: str, tenant: str | None = None) -> int | None:
        """リセットトークンを発行しメールを送る。ユーザー不在でも黙って成功する。

        監査ログへ「誰の」要求かを残せるよう、トークンを発行した利用者の ID を
        返す（宛先不明のときは ``None``）。API 応答はどちらの場合も同じで、
        存在の有無は呼び出し側から漏らさない。
        """
        user = account_signing_in(session, email, tenant)
        if user is None or not user.is_active:
            logger.info("password_reset_requested_unknown_email")
            return None
        if not user.has_local_password:
            # ⚠ **リセットでローカル認証を生やさない**（ADR-0038）。パスワードを
            # 持たない利用者にここで新しい値を設定させると、「この利用者は SSO でしか
            # 入れない」が黙って崩れる。持たせるなら管理者が明示的に設定する。
            logger.info("password_reset_requested_without_local_password")
            return None

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
        return user.id

    def invite(self, session: Session, user: User, *, place: str) -> bool:
        """招待のメールを送る（ADR-0065）。本人が自分でパスワードを決める。送れたら真。

        ⚠ **招待した人はパスワードを知らない。** システム管理者が最初のテナント管理者を
        指名するとき、初期パスワードを決めて渡すと、システム管理者がその人として入れて
        しまう（中身を見ない約束が崩れる。ADR-0061）。
        ⚠ **リンクを応答に載せない。** 載せると、招待した人がそのまま使える。
        """
        token = secrets.token_urlsafe(32)
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_token(token),
                purpose=INVITATION,
                expires_at=utcnow() + INVITATION_TTL,
            )
        )
        session.flush()
        link = f"{settings.app_base_url.rstrip('/')}/reset-password?token={token}"
        try:
            SendEmail(self._sender).execute(
                EmailMessage(
                    to=user.email,
                    subject="You are invited",
                    body=(
                        f"An account was prepared for you ({place}).\n"
                        f"Open the following link to choose your password:\n{link}\n\n"
                        f"The link expires in {INVITATION_TTL.days} days."
                    ),
                )
            )
        except EmailSendingDisabledError:
            logger.warning("invitation_mail_disabled")
            return False
        return True

    def reset(self, session: Session, token: str, new_password: str) -> int | None:
        """トークンを検証してパスワードを更新する。

        成功したら対象利用者の ID（監査ログの「誰が」に使う）、失敗なら ``None``。
        """
        from werkzeug.security import generate_password_hash

        row = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(token)))
        if row is None or row.used_at is not None or row.expires_at < utcnow():
            return None
        user = session.get(User, row.user_id)
        if user is None or not user.is_active:
            return None
        if not user.has_local_password and row.purpose != INVITATION:
            # 発行のあとでパスワードを取り上げられた場合（ADR-0038）。券が残っていても
            # 通さない。招待（ADR-0065）だけは、最初のパスワードを決めるためのもの。
            return None
        user.password_hash = generate_password_hash(new_password)
        # 再設定の前に始まったログインは、次の更新で終わる（ADR-0057）
        user.end_sessions()
        row.used_at = utcnow()
        session.flush()
        return user.id


__all__ = ["INVITATION", "INVITATION_TTL", "PasswordResetService"]
