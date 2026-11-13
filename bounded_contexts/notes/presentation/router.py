"""notes context API (shared notes; sample for ADR-0078 §6).

Authorization is applied in two stages.

1. **May the feature be used** -- the token's scope (``note:view`` / ``note:write``). The dependency
   checks it without hitting the DB (ADR-0076 §5).
2. **May this particular note be handled** -- owner and group membership. The use case checks them in the DB.

Resource IDs (like ``note:42:edit``) are not put in scopes.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from bounded_contexts.notes.application.dto.note_dto import NoteDTO, NoteInput
from bounded_contexts.notes.application.use_cases.note_book import NoteBook
from bounded_contexts.notes.domain.value_objects.note_text import BODY_MAX_LENGTH, TITLE_MAX_LENGTH
from bounded_contexts.notes.infrastructure.sql_group_membership import SqlGroupMembership
from bounded_contexts.notes.infrastructure.sql_note_repository import SqlNoteRepository
from presentation.fastapi.dependencies.auth import require_permission
from presentation.fastapi.dependencies.tenant import TenantIdDep
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db

router = APIRouter(prefix="/api/notes", tags=["notes"])
logger = logging.getLogger(__name__)


class NoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH, pattern=r"\S")
    body: str = Field(default="", max_length=BODY_MAX_LENGTH)
    #: Group shared with. ``null`` means private
    shared_group_id: int | None = None

    def to_input(self) -> NoteInput:
        return NoteInput(title=self.title, body=self.body, shared_group_id=self.shared_group_id)


class NoteResponse(BaseModel):
    id: int
    title: str
    body: str
    shared_group_id: int | None
    mine: bool
    #: Whether the caller may modify/delete this note (is the owner). The UI combines it with the note:write scope
    can_change: bool

    @classmethod
    def of(cls, dto: NoteDTO) -> NoteResponse:
        return cls(
            id=dto.id,
            title=dto.title,
            body=dto.body,
            shared_group_id=dto.shared_group_id,
            mine=dto.mine,
            can_change=dto.can_change,
        )


class ShareTargetResponse(BaseModel):
    id: int
    name: str


def get_note_book(db: Annotated[Session, Depends(get_db)], tenant_id: TenantIdDep) -> NoteBook:
    return NoteBook(SqlNoteRepository(db, tenant_id), SqlGroupMembership(db, tenant_id))


NoteBookDep = Annotated[NoteBook, Depends(get_note_book)]
ReaderDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("note:view"))]
WriterDep = Annotated[AuthenticatedPrincipal, Depends(require_permission("note:write"))]


@router.get("", response_model=list[NoteResponse])
def list_notes(principal: ReaderDep, book: NoteBookDep) -> list[NoteResponse]:
    """The caller's own notes and notes shared with groups the caller belongs to."""
    return [NoteResponse.of(dto) for dto in book.list_readable(principal.user_id)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=NoteResponse)
def create_note(body: NoteRequest, principal: WriterDep, book: NoteBookDep) -> NoteResponse:
    dto = book.create(principal.user_id, body.to_input())
    logger.info("note_created", extra={"note_id": dto.id})
    return NoteResponse.of(dto)


@router.get("/share-targets", response_model=list[ShareTargetResponse])
def list_share_targets(principal: WriterDep, book: NoteBookDep) -> list[ShareTargetResponse]:
    """Groups that may be chosen as the share target (only those the caller belongs to)."""
    return [ShareTargetResponse(id=t.id, name=t.name) for t in book.share_targets(principal.user_id)]


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(note_id: int, principal: ReaderDep, book: NoteBookDep) -> NoteResponse:
    return NoteResponse.of(book.get(principal.user_id, note_id))


@router.put("/{note_id}", response_model=NoteResponse)
def update_note(note_id: int, body: NoteRequest, principal: WriterDep, book: NoteBookDep) -> NoteResponse:
    dto = book.update(principal.user_id, note_id, body.to_input())
    logger.info("note_updated", extra={"note_id": note_id})
    return NoteResponse.of(dto)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, principal: WriterDep, book: NoteBookDep) -> None:
    book.delete(principal.user_id, note_id)
    logger.info("note_deleted", extra={"note_id": note_id})
