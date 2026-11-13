from abc import ABC, abstractmethod

from bounded_contexts.email_sender.domain.email_message import EmailMessage


class EmailSendingDisabledError(Exception):
    """Raised when email sending is disabled (``MAIL_ENABLED`` not set)."""


class IEmailSender(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> None: ...
