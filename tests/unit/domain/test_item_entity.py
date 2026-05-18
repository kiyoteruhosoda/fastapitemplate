from src.domain.entities.item import Item
from src.domain.value_objects.item_name import ItemName


def test_create_item() -> None:
    item = Item.create(id=1, name="widget")
    assert item.id == 1
    assert isinstance(item.name, ItemName)
    assert item.name_value == "widget"


def test_name_value_delegates_to_value_object() -> None:
    item = Item.create(id=42, name="gadget")
    assert item.name_value == item.name.value
