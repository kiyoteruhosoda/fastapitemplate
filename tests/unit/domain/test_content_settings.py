"""コンテンツ設定の定義と値の確かめ（ADR-0085）。"""

from __future__ import annotations

import pytest

from bounded_contexts.content_settings.domain.content_settings import ContentSettings
from bounded_contexts.content_settings.domain.definitions import (
    CONTENT_SETTINGS,
    ITEM_LIST_ORDER,
    ContentSettingDefinition,
    ContentSettingType,
)
from bounded_contexts.content_settings.domain.exceptions import (
    InvalidContentSettingValueError,
    UnknownContentSettingError,
)
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder

_LIMIT = ContentSettingDefinition(
    key="page_size", value_type=ContentSettingType.INTEGER, default=20, minimum=1, maximum=100
)
_FLAG = ContentSettingDefinition(key="show_names", value_type=ContentSettingType.BOOLEAN, default=False)
_ALL = (ITEM_LIST_ORDER, _LIMIT, _FLAG)


def test_keys_are_unique_and_defaults_are_acceptable() -> None:
    keys = [d.key for d in CONTENT_SETTINGS]
    assert len(keys) == len(set(keys))
    settings = ContentSettings({})
    for definition in CONTENT_SETTINGS:
        assert settings.checked({definition.key: definition.default}) == {definition.key: definition.default}


def test_the_item_order_choices_match_what_the_items_list_understands() -> None:
    assert set(ITEM_LIST_ORDER.choices) == {o.value for o in ItemListOrder}


def test_unsaved_settings_read_as_their_default() -> None:
    settings = ContentSettings({}, _ALL)
    assert settings.value_of(ITEM_LIST_ORDER) == "oldest"
    assert not settings.is_stored(ITEM_LIST_ORDER.key)


def test_saved_values_win_over_the_default() -> None:
    settings = ContentSettings({"item_list_order": "name", "page_size": 50}, _ALL)
    assert settings.value_of(ITEM_LIST_ORDER) == "name"
    assert settings.value_of(_LIMIT) == 50


def test_a_saved_value_the_definition_no_longer_accepts_reads_as_the_default() -> None:
    settings = ContentSettings({"item_list_order": "removed-choice"}, _ALL)
    assert settings.value_of(ITEM_LIST_ORDER) == "oldest"
    assert not settings.is_stored(ITEM_LIST_ORDER.key)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("item_list_order", "random"),
        ("item_list_order", 1),
        ("page_size", 0),
        ("page_size", 101),
        ("page_size", "10"),
        ("page_size", True),
        ("show_names", "yes"),
        ("show_names", 1),
    ],
)
def test_values_outside_the_definition_are_refused(key: str, value: object) -> None:
    with pytest.raises(InvalidContentSettingValueError):
        ContentSettings({}, _ALL).checked({key: value})


def test_unknown_keys_are_refused() -> None:
    with pytest.raises(UnknownContentSettingError):
        ContentSettings({}, _ALL).checked({"nope": "x"})


def test_none_resets_to_the_default() -> None:
    assert ContentSettings({"page_size": 50}, _ALL).checked({"page_size": None}) == {"page_size": None}
