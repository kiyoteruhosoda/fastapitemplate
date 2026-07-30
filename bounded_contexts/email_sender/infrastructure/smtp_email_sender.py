"""``IEmailSender`` の SMTP 実装（接続設定はシステム設定から取得）。"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from bounded_contexts.email_sender.domain.email_message import EmailMessage
from bounded_contexts.email_sender.domain.email_sender import IEmailSender
from shared.kernel.settings.settings import settings


class SmtpEmailSender(IEmailSender):
    def send(self, message: EmailMessage) -> None:
        mime = MIMEText(message.body, "plain", "utf-8")
        mime["Subject"] = message.subject
        mime["From"] = settings.mail_default_sender or settings.mail_username
        mime["To"] = message.to

        if settings.mail_use_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(settings.mail_server, settings.mail_port)
        else:
            client = smtplib.SMTP(settings.mail_server, settings.mail_port)
        try:
            if settings.mail_use_tls and not settings.mail_use_ssl:
                client.starttls()
            if settings.mail_username:
                client.login(settings.mail_username, settings.mail_password)
            client.send_message(mime)
        finally:
            client.quit()
