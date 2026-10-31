from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.example.domain.entities.item import Item


@dataclass(frozen=True)
class ItemDTO:
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, item: Item) -> ItemDTO:
        return cls(id=item.id, name=item.name_value, created_at=item.created_at, updated_at=item.updated_at)
