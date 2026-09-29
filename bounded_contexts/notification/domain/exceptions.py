class NotificationError(Exception):
    """notification コンテキストのドメイン例外の基底。``code`` は画面へ返す安定キー。"""

    code = "notification_error"

    def __init__(self, code: str | None = None) -> None:
        super().__init__(code or self.code)
        if code is not None:
            self.code = code


class NotificationValidationError(NotificationError):
    """お知らせの中身・宛先・購読が正しくない。"""

    code = "invalid_notification"


class NotificationNotFoundError(NotificationError):
    """その利用者宛てのお知らせが無い（他人宛てのものも「無い」と答える）。"""

    code = "notification_not_found"

    def __init__(self, notification_id: int | None = None) -> None:
        super().__init__()
        self.notification_id = notification_id


class AudienceNotFoundError(NotificationError):
    """宛先に選んだグループ・利用者が無い（``group_not_found`` / ``user_not_found``）。"""

    code = "audience_not_found"

    def __init__(self, kind: str) -> None:
        super().__init__(f"{kind}_not_found")
