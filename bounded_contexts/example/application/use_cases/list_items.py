from bounded_contexts.example.application.dto.item_dto import ItemDTO
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder
from shared.domain.page import Page, PageRequest


class ListItemsUseCase:
    def __init__(self, repository: IItemRepository) -> None:
        self._repository = repository

    def execute(self, order: ItemListOrder, page: PageRequest) -> Page[ItemDTO]:
        found = self._repository.find_page(order, page)
        return Page(entries=[ItemDTO.of(item) for item in found.entries], total=found.total)
