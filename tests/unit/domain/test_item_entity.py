from datetime import datetime

from bounded_contexts.example.domain.entities.item import Item
from bounded_contexts.example.domain.value_objects.item_name import ItemName

_AT = datetime(2026, 10, 31, 0, 0, 0)


def test_create_item() -> None:
    item = Item(id=1, name=ItemName("sample"), created_at=_AT, updated_at=_AT)
    assert item.id == 1
    assert item.name_value == "sample"
