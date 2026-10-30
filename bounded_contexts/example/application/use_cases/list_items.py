from bounded_contexts.example.application.dto.item_dto import ItemDTO
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository
from bounded_contexts.example.domain.value_objects.item_list_order import ItemListOrder


class ListItemsUseCase:
    def __init__(self, repository: IItemRepository) -> None:
        self._repository = repository

    def execute(self, order: ItemListOrder = ItemListOrder.OLDEST) -> list[ItemDTO]:
        items = self._repository.find_all(order)
        return [ItemDTO(id=item.id, name=item.name_value) for item in items]
