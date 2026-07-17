import pytest

from bounded_contexts.example.domain.value_objects.item_name import ItemName


def test_valid_name() -> None:
    assert ItemName("hello").value == "hello"


def test_empty_name_rejected() -> None:
    with pytest.raises(ValueError):
        ItemName("")


def test_blank_name_rejected() -> None:
    with pytest.raises(ValueError):
        ItemName("   ")


def test_too_long_name_rejected() -> None:
    with pytest.raises(ValueError):
        ItemName("a" * 256)
