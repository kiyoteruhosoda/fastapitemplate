from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.example.domain.value_objects.item_name import ItemName


@dataclass
class Item:
    id: int
    name: ItemName
    created_at: datetime
    updated_at: datetime

    @property
    def name_value(self) -> str:
        return self.name.value
