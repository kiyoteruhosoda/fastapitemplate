"""notes コンテキストの API（共有メモ。ADR-0070 の見本）。

認可は 2 段で掛ける。

1. **機能を使えるか** —— トークンの scope（``note:view`` / ``note:write``）。依存関数が
   DB を引かずに確かめる（ADR-0041）。
2. **この 1 件を扱えるか** —— 持ち主とグループの所属。ユースケースが DB を引いて確かめる。

scope に資源の ID（``note:42:edit`` のようなもの）は載せない。
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
    #: 共有先のグループ。``null`` は自分だけ
    shared_group_id: int | None = None

    def to_input(self) -> NoteInput:
        return NoteInput(title=self.title, body=self.body, shared_group_id=self.shared_group_id)


class NoteResponse(BaseModel):
    id: int
    title: str
    body: str
    shared_group_id: int | None
    mine: bool
    #: この 1 件を書き換え・削除できるか（持ち主か）。画面は scope の note:write と合わせて出し分ける
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
async def list_notes(principal: ReaderDep, book: NoteBookDep) -> list[NoteResponse]:
    """自分のメモと、自分が入っているグループに共有されたメモ。"""
    return [NoteResponse.of(dto) for dto in book.list_readable(principal.user_id)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=NoteResponse)
async def create_note(body: NoteRequest, principal: WriterDep, book: NoteBookDep) -> NoteResponse:
    dto = book.create(principal.user_id, body.to_input())
    logger.info("note_created", extra={"note_id": dto.id})
    return NoteResponse.of(dto)


@router.get("/share-targets", response_model=list[ShareTargetResponse])
async def list_share_targets(principal: WriterDep, book: NoteBookDep) -> list[ShareTargetResponse]:
    """共有先に選べるグループ（自分が入っているものだけ）。"""
    return [ShareTargetResponse(id=t.id, name=t.name) for t in book.share_targets(principal.user_id)]


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(note_id: int, principal: ReaderDep, book: NoteBookDep) -> NoteResponse:
    return NoteResponse.of(book.get(principal.user_id, note_id))


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(note_id: int, body: NoteRequest, principal: WriterDep, book: NoteBookDep) -> NoteResponse:
    dto = book.update(principal.user_id, note_id, body.to_input())
    logger.info("note_updated", extra={"note_id": note_id})
    return NoteResponse.of(dto)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, principal: WriterDep, book: NoteBookDep) -> None:
    book.delete(principal.user_id, note_id)
    logger.info("note_deleted", extra={"note_id": note_id})
