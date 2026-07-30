"""メール送信ユースケース（送信可否の判定を含むトランザクション境界）。"""

from __future__ import annotations

from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.email_sender import (
    EmailSendingDisabledError,
    IEmailSender,
)
from shared.kernel.settings.settings import settings


class SendEmail:
    def __init__(self, sender: IEmailSender) -> None:
        self._sender = sender

    def execute(self, message: EmailMessage) -> None:
        if not settings.mail_enabled:
            raise EmailSendingDisabledError("Mail is disabled. Enable MAIL_ENABLED in system settings.")
        self._sender.send(message)
