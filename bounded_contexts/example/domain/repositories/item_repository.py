from abc import ABC, abstractmethod

from bounded_contexts.example.domain.entities.item import Item
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder
from shared.domain.page import Page, PageRequest


class IItemRepository(ABC):
    @abstractmethod
    def save(self, name: str) -> Item: ...

    @abstractmethod
    def find_page(self, order: ItemListOrder, page: PageRequest) -> Page[Item]: ...
