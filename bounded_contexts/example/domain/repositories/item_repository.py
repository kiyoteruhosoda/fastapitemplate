from abc import ABC, abstractmethod

from bounded_contexts.example.domain.entities.item import Item


class IItemRepository(ABC):
    @abstractmethod
    def save(self, name: str) -> Item: ...

    @abstractmethod
    def find_all(self) -> list[Item]: ...
