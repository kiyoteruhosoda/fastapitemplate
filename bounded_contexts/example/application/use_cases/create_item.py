from bounded_contexts.example.application.dto.item_dto import ItemDTO
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository


class CreateItemUseCase:
    def __init__(self, repository: IItemRepository) -> None:
        self._repository = repository

    def execute(self, name: str) -> ItemDTO:
        item = self._repository.save(name)
        return ItemDTO(id=item.id, name=item.name_value)
