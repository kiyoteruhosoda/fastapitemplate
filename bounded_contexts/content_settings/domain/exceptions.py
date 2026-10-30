"""コンテンツ設定の誤り。画面にはエラーコードで返す。"""

from __future__ import annotations


class ContentSettingError(Exception):
    code = "invalid_content_setting"

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class UnknownContentSettingError(ContentSettingError):
    """定義に無い項目。"""

    code = "unknown_content_setting"


class InvalidContentSettingValueError(ContentSettingError):
    """型・選べる値・範囲に合わない値。"""

    code = "invalid_content_setting"


__all__ = ["ContentSettingError", "InvalidContentSettingValueError", "UnknownContentSettingError"]
