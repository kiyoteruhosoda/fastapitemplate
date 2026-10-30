"""コンテンツ設定を読む・変える（ADR-0085）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from bounded_contexts.content_settings.domain.content_settings import ContentSettings, SettingValue
from bounded_contexts.content_settings.domain.definitions import ContentSettingDefinition
from bounded_contexts.content_settings.domain.repositories.content_setting_repository import (
    IContentSettingRepository,
)


@dataclass(frozen=True)
class ContentSettingEntry:
    key: str
    value_type: str
    value: SettingValue
    default: SettingValue
    #: テナントが値を保存しているか（偽なら既定値で動いている）
    stored: bool
    choices: tuple[str, ...]
    minimum: int | None
    maximum: int | None


class ContentSettingsBook:
    def __init__(self, repository: IContentSettingRepository) -> None:
        self._repository = repository

    def _current(self) -> ContentSettings:
        return ContentSettings(self._repository.stored())

    def entries(self) -> list[ContentSettingEntry]:
        current = self._current()
        return [
            ContentSettingEntry(
                key=d.key,
                value_type=d.value_type.value,
                value=current.value_of(d),
                default=d.default,
                stored=current.is_stored(d.key),
                choices=d.choices,
                minimum=d.minimum,
                maximum=d.maximum,
            )
            for d in current.definitions
        ]

    def value_of(self, definition: ContentSettingDefinition) -> SettingValue:
        return self._current().value_of(definition)

    def change(self, changes: Mapping[str, object]) -> list[str]:
        """変えた項目のキー（並べ替え済み）を返す。誤りがあれば何も変えずに例外を上げる。"""
        accepted = self._current().checked(changes)
        for key, value in accepted.items():
            if value is None:
                self._repository.remove(key)
            else:
                self._repository.put(key, value)
        return sorted(accepted)


__all__ = ["ContentSettingEntry", "ContentSettingsBook"]
