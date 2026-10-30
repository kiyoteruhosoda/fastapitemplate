"""``INoteRepository`` の SQLAlchemy 実装。テナントはコンストラクタで受け取る（ADR-0062）。"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from bounded_contexts.notes.domain.entities.note import Note, NoteContent
from bounded_contexts.notes.domain.repositories.note_repository import INoteRepository
from bounded_contexts.notes.domain.value_objects.note_text import NoteBody, NoteTitle
from bounded_contexts.notes.domain.value_objects.viewer import Viewer
from bounded_contexts.notes.infrastructure.note_model import NoteModel


class SqlNoteRepository(INoteRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def add(self, owner_user_id: int, content: NoteContent) -> Note:
        row = NoteModel(tenant_id=self._tenant_id, owner_user_id=owner_user_id)
        _write(row, content)
        self._session.add(row)
        self._session.flush()
        return _to_note(row)

    def get(self, note_id: int) -> Note | None:
        row = self._row(note_id)
        return None if row is None else _to_note(row)

    def find_readable(self, viewer: Viewer) -> list[Note]:
        """読めるメモの一覧。決まりは ``Note.readable_by`` と同じものを SQL で書く。

        1 件ずつ ``readable_by`` で篩うと、テナントの全部のメモを読むことになる。
        """
        readable = or_(
            NoteModel.owner_user_id == viewer.user_id,
            NoteModel.shared_group_id.in_(viewer.group_ids),
        )
        rows = self._session.scalars(
            select(NoteModel).where(NoteModel.tenant_id == self._tenant_id, readable).order_by(NoteModel.id)
        ).all()
        return [_to_note(row) for row in rows]

    def replace(self, note: Note) -> None:
        row = self._row(note.id)
        if row is not None:
            _write(row, note.content)
            self._session.flush()

    def remove(self, note_id: int) -> None:
        row = self._row(note_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def _row(self, note_id: int) -> NoteModel | None:
        return self._session.scalars(
            select(NoteModel).where(NoteModel.id == note_id, NoteModel.tenant_id == self._tenant_id)
        ).one_or_none()


def _write(row: NoteModel, content: NoteContent) -> None:
    row.title = content.title.value
    row.body = content.body.value
    row.shared_group_id = content.shared_group_id


def _to_note(row: NoteModel) -> Note:
    return Note(
        id=row.id,
        owner_user_id=row.owner_user_id,
        content=NoteContent(
            title=NoteTitle(row.title),
            body=NoteBody(row.body),
            shared_group_id=row.shared_group_id,
        ),
    )
