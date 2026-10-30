from abc import ABC, abstractmethod

from bounded_contexts.example.domain.entities.item import Item
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder


class IItemRepository(ABC):
    @abstractmethod
    def save(self, name: str) -> Item: ...

    @abstractmethod
    def find_all(self, order: ItemListOrder = ItemListOrder.OLDEST) -> list[Item]: ...
