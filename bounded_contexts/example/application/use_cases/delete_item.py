from bounded_contexts.example.domain.repositories.item_repository import IItemRepository


class DeleteItemUseCase:
    def __init__(self, repository: IItemRepository) -> None:
        self._repository = repository

    def execute(self, item_id: int) -> None:
        self._repository.delete(item_id)
