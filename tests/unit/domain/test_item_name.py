import pytest

from src.domain.value_objects.item_name import ItemName


def test_valid_name() -> None:
    assert ItemName("hello").value == "hello"


def test_empty_name_raises() -> None:
    with pytest.raises(ValueError):
        ItemName("")


def test_whitespace_only_raises() -> None:
    with pytest.raises(ValueError):
        ItemName("   ")


def test_too_long_name_raises() -> None:
    with pytest.raises(ValueError):
        ItemName("x" * 256)


def test_max_length_is_accepted() -> None:
    ItemName("x" * 255)


def test_immutability() -> None:
    name = ItemName("test")
    with pytest.raises(AttributeError):
        name.value = "other"  # type: ignore[misc]
