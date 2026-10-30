"""テナントのコンテンツ設定（定義と保存した値を合わせたもの）。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from bounded_contexts.content_settings.domain.definitions import (
    CONTENT_SETTINGS,
    ContentSettingDefinition,
    ContentSettingType,
)
from bounded_contexts.content_settings.domain.exceptions import (
    InvalidContentSettingValueError,
    UnknownContentSettingError,
)

SettingValue = str | bool | int


def _accepts(definition: ContentSettingDefinition, value: object) -> bool:
    if definition.value_type == ContentSettingType.CHOICE:
        return isinstance(value, str) and value in definition.choices
    if definition.value_type == ContentSettingType.BOOLEAN:
        return isinstance(value, bool)
    # bool は int の下位型なので先に外す
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    low = definition.minimum if definition.minimum is not None else value
    high = definition.maximum if definition.maximum is not None else value
    return low <= value <= high


class ContentSettings:
    """定義に、テナントが保存した値を重ねたもの。保存していない項目は既定値で読む。

    保存した値が定義に合わなくなったとき（選べる値を減らした等）は、既定値で読む。
    """

    def __init__(
        self,
        stored: Mapping[str, object],
        definitions: Sequence[ContentSettingDefinition] = CONTENT_SETTINGS,
    ) -> None:
        self._definitions = {d.key: d for d in definitions}
        self._stored = {k: v for k, v in stored.items() if k in self._definitions}

    @property
    def definitions(self) -> tuple[ContentSettingDefinition, ...]:
        return tuple(self._definitions.values())

    def is_stored(self, key: str) -> bool:
        return key in self._stored and _accepts(self._definitions[key], self._stored[key])

    def value_of(self, definition: ContentSettingDefinition) -> SettingValue:
        if self.is_stored(definition.key):
            value = self._stored[definition.key]
            if isinstance(value, str | bool | int):
                return value
        return definition.default

    def checked(self, changes: Mapping[str, object]) -> dict[str, SettingValue | None]:
        """変更を確かめて返す。``None`` は「既定値へ戻す」。1 つでも誤りがあれば何も通さない。"""
        accepted: dict[str, SettingValue | None] = {}
        for key, value in changes.items():
            definition = self._definitions.get(key)
            if definition is None:
                raise UnknownContentSettingError(key)
            if value is None:
                accepted[key] = None
                continue
            if not _accepts(definition, value) or not isinstance(value, str | bool | int):
                raise InvalidContentSettingValueError(key)
            accepted[key] = value
        return accepted


__all__ = ["ContentSettings", "SettingValue"]
