class NotificationError(Exception):
    """Base of the notification context's domain exceptions. ``code`` is a stable key returned to the UI."""

    code = "notification_error"

    def __init__(self, code: str | None = None) -> None:
        super().__init__(code or self.code)
        if code is not None:
            self.code = code


class NotificationValidationError(NotificationError):
    """Invalid notification content, audience or subscription."""

    code = "invalid_notification"


class NotificationNotFoundError(NotificationError):
    """No such notification for that user (ones addressed to others are also reported as missing)."""

    code = "notification_not_found"

    def __init__(self, notification_id: int | None = None) -> None:
        super().__init__()
        self.notification_id = notification_id


class AudienceNotFoundError(NotificationError):
    """The group or user chosen as the audience does not exist (``group_not_found`` / ``user_not_found``)."""

    code = "audience_not_found"

    def __init__(self, kind: str) -> None:
        super().__init__(f"{kind}_not_found")
