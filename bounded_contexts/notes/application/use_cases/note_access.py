"""1 件ずつの可否（ADR-0078 §6）。

トークンの scope で「メモの機能を使えるか」は依存関数が確かめ済み。ここでは
「この人が、この 1 件を」を DB の持ち主・所属で確かめる。
"""

from bounded_contexts.notes.application.dto.note_dto import NoteInput
from bounded_contexts.notes.domain.entities.note import Note, NoteContent
from bounded_contexts.notes.domain.exceptions import (
    NoteNotFoundError,
    NoteNotOwnedError,
    ShareGroupNotJoinedError,
)
from bounded_contexts.notes.domain.repositories.note_repository import INoteRepository
from bounded_contexts.notes.domain.value_objects.note_text import NoteBody, NoteTitle
from bounded_contexts.notes.domain.value_objects.viewer import Viewer


def readable_note(notes: INoteRepository, viewer: Viewer, note_id: int) -> Note:
    """読めるメモを返す。無いものも読めないものも同じく :class:`NoteNotFoundError`。"""
    note = notes.get(note_id)
    if note is None or not note.readable_by(viewer):
        raise NoteNotFoundError
    return note


def changeable_note(notes: INoteRepository, viewer: Viewer, note_id: int) -> Note:
    """変えてよいメモを返す。読めるが持ち主でなければ :class:`NoteNotOwnedError`。"""
    note = readable_note(notes, viewer, note_id)
    if not note.changeable_by(viewer):
        raise NoteNotOwnedError
    return note


def content_for(viewer: Viewer, data: NoteInput, current: Note | None = None) -> NoteContent:
    """書き手の入力を中身にする。共有先は自分が入っているグループだけ。

    書き換えでは、いまの共有先はそのまま残せる（共有した後に自分がグループを抜けても、
    題名を直しただけで断られないように）。
    """
    unchanged = current is not None and current.content.shared_group_id == data.shared_group_id
    if not unchanged and not viewer.can_share_with(data.shared_group_id):
        raise ShareGroupNotJoinedError
    return NoteContent(
        title=NoteTitle(data.title),
        body=NoteBody(data.body),
        shared_group_id=data.shared_group_id,
    )
