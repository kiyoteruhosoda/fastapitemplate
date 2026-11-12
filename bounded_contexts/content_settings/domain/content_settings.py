"""A tenant's content settings (the definitions combined with the saved values)."""

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
    # bool is a subtype of int, so rule it out first
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    low = definition.minimum if definition.minimum is not None else value
    high = definition.maximum if definition.maximum is not None else value
    return low <= value <= high


class ContentSettings:
    """The definitions with the tenant's saved values laid over them. Unsaved items read as defaults.

    When a saved value no longer fits its definition (e.g. a choice was removed), it reads as the default.
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
        """Check the changes and return them. ``None`` means "reset to default". One error rejects them all."""
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
