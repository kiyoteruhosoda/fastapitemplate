import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.application.use_cases.create_item import CreateItemUseCase
from src.application.use_cases.list_items import ListItemsUseCase
from src.presentation.api.dependencies import (
    get_create_item_use_case,
    get_list_items_use_case,
)
from src.presentation.api.schemas.item import ItemCreate, ItemResponse

router = APIRouter(prefix="/items", tags=["items"])
logger = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ItemResponse)
async def create_item(
    body: ItemCreate,
    use_case: Annotated[CreateItemUseCase, Depends(get_create_item_use_case)],
) -> ItemResponse:
    dto = use_case.execute(body.name)
    logger.info("item_created", extra={"item_id": dto.id, "item_name": dto.name})
    return ItemResponse(id=dto.id, name=dto.name)


@router.get("", response_model=list[ItemResponse])
async def list_items(
    use_case: Annotated[ListItemsUseCase, Depends(get_list_items_use_case)],
) -> list[ItemResponse]:
    dtos = use_case.execute()
    return [ItemResponse(id=dto.id, name=dto.name) for dto in dtos]
