from dataclasses import dataclass

from bounded_contexts.example.domain.value_objects.item_name import ItemName


@dataclass
class Item:
    id: int
    name: ItemName

    @classmethod
    def create(cls, *, id: int, name: str) -> "Item":
        return cls(id=id, name=ItemName(name))

    @property
    def name_value(self) -> str:
        return self.name.value
