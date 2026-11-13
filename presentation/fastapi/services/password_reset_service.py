"""Password reset (token issuance, email sending, resetting).

Tokens are never stored in plaintext; only the SHA-256 hash is stored.
Whether a user exists cannot be told from the API response (against enumeration attacks).

⚠ **Not issued to users without a password** (ADR-0076 §6). Allowing a reset would silently
break "this user can only sign in via SSO". The response is the same as for a missing user.
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
#: Invitation validity period. ⚠ Not a setting (not a value operators should revisit).
INVITATION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordResetService:
    def __init__(self, sender: IEmailSender | None = None) -> None:
        self._sender = sender or SmtpEmailSender()

    def request_reset(self, session: Session, email: str, tenant: str | None = None) -> int | None:
        """Issue a reset token and send the email. Silently succeeds even if the user doesn't exist.

        Returns the ID of the user the token was issued for, so the audit log can record
        "whose" request it was (``None`` if no recipient). The API response is the same either
        way, so existence is not leaked to the caller.
        """
        user = account_signing_in(session, email, tenant)
        if user is None or not user.is_active:
            logger.info("password_reset_requested_unknown_email")
            return None
        if not user.has_local_password:
            # ⚠ **A reset must not create local authentication** (ADR-0076 §6). Letting a user
            # without a password set one here would silently break "this user can only sign in
            # via SSO". If they should have one, an administrator sets it explicitly.
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
        """Send the invitation email (ADR-0079 §5). The person sets their own password. True if sent.

        ⚠ **The inviter never knows the password.** If a system administrator appointing the
        first tenant administrator chose and handed over an initial password, the system
        administrator could sign in as that person (breaking the promise not to look at tenant
        data; ADR-0079 §1).
        ⚠ **The link is not included in the response.** Otherwise the inviter could use it.
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
        """Verify the token and update the password.

        Returns the target user's ID on success (used as "who" in the audit log), ``None`` on
        failure.
        """
        from werkzeug.security import generate_password_hash

        row = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash_token(token)))
        if row is None or row.used_at is not None or row.expires_at < utcnow():
            return None
        user = session.get(User, row.user_id)
        if user is None or not user.is_active:
            return None
        if not user.has_local_password and row.purpose != INVITATION:
            # The password was taken away after issuance (ADR-0076 §6). Reject even if the token
            # remains. Only invitations (ADR-0079 §5) exist to set the first password.
            return None
        user.password_hash = generate_password_hash(new_password)
        # Logins started before the reset end at their next refresh (ADR-0076 §8)
        user.end_sessions()
        row.used_at = utcnow()
        session.flush()
        return user.id


__all__ = ["INVITATION", "INVITATION_TTL", "PasswordResetService"]
