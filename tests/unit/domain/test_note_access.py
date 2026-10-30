"""メモ 1 件ずつの可否（ADR-0070）。"""

from __future__ import annotations

import pytest

from bounded_contexts.notes.domain.entities.note import Note, NoteContent
from bounded_contexts.notes.domain.exceptions import NoteValidationError
from bounded_contexts.notes.domain.value_objects.note_text import NoteBody, NoteTitle
from bounded_contexts.notes.domain.value_objects.viewer import Viewer

_OWNER = 1
_GROUP = 10


def _note(shared_group_id: int | None) -> Note:
    content = NoteContent(title=NoteTitle("t"), body=NoteBody(""), shared_group_id=shared_group_id)
    return Note(id=1, owner_user_id=_OWNER, content=content)


def _viewer(user_id: int, *groups: int) -> Viewer:
    return Viewer(user_id=user_id, group_ids=frozenset(groups))


def test_the_owner_reads_and_changes() -> None:
    note = _note(None)
    assert note.readable_by(_viewer(_OWNER))
    assert note.changeable_by(_viewer(_OWNER))


def test_a_private_note_is_closed_to_others() -> None:
    assert not _note(None).readable_by(_viewer(2, _GROUP))


def test_group_members_read_but_do_not_change() -> None:
    note = _note(_GROUP)
    member = _viewer(2, _GROUP)
    assert note.readable_by(member)
    assert not note.changeable_by(member)
    assert not note.readable_by(_viewer(3, 99))


def test_you_share_only_with_your_own_groups() -> None:
    viewer = _viewer(2, _GROUP)
    assert viewer.can_share_with(None)
    assert viewer.can_share_with(_GROUP)
    assert not viewer.can_share_with(99)


@pytest.mark.parametrize("title", ["", "   ", "x" * 101])
def test_titles_must_say_something_short(title: str) -> None:
    with pytest.raises(NoteValidationError):
        NoteTitle(title)
