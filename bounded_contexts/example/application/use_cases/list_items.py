from bounded_contexts.example.application.dto.item_dto import ItemDTO
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository


class ListItemsUseCase:
    def __init__(self, repository: IItemRepository) -> None:
        self._repository = repository

    def execute(self) -> list[ItemDTO]:
        items = self._repository.find_all()
        return [ItemDTO(id=item.id, name=item.name_value) for item in items]
