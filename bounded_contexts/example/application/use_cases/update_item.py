from bounded_contexts.example.application.dto.item_dto import ItemDTO
from bounded_contexts.example.domain.repositories.item_repository import IItemRepository


class UpdateItemUseCase:
    def __init__(self, repository: IItemRepository) -> None:
        self._repository = repository

    def execute(self, item_id: int, name: str) -> ItemDTO:
        return ItemDTO.of(self._repository.rename(item_id, name))
