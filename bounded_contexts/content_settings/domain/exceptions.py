"""Content setting errors. Returned to the UI as error codes."""

from __future__ import annotations


class ContentSettingError(Exception):
    code = "invalid_content_setting"

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class UnknownContentSettingError(ContentSettingError):
    """An item that is not defined."""

    code = "unknown_content_setting"


class InvalidContentSettingValueError(ContentSettingError):
    """A value that does not match the type, choices or range."""

    code = "invalid_content_setting"


__all__ = ["ContentSettingError", "InvalidContentSettingValueError", "UnknownContentSettingError"]
