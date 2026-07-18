from bounded_contexts.example.domain.entities.item import Item


def test_create_item() -> None:
    item = Item.create(id=1, name="sample")
    assert item.id == 1
    assert item.name_value == "sample"
