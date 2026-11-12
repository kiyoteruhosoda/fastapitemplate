"""Per-note permission checks (ADR-0078 §6).

The dependency has already checked via the token's scope whether the notes feature may be used.
Here we check "this person, this note" against the owner and memberships in the DB.
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
    """Return a readable note. Missing and unreadable both raise :class:`NoteNotFoundError`."""
    note = notes.get(note_id)
    if note is None or not note.readable_by(viewer):
        raise NoteNotFoundError
    return note


def changeable_note(notes: INoteRepository, viewer: Viewer, note_id: int) -> Note:
    """Return a note the caller may change. Readable but not owned raises :class:`NoteNotOwnedError`."""
    note = readable_note(notes, viewer, note_id)
    if not note.changeable_by(viewer):
        raise NoteNotOwnedError
    return note


def content_for(viewer: Viewer, data: NoteInput, current: Note | None = None) -> NoteContent:
    """Turn the writer's input into content. The share target must be a group the caller belongs to.

    An update may keep the current share target (so that fixing just the title isn't refused
    after the caller has left the group it was shared with).
    """
    unchanged = current is not None and current.content.shared_group_id == data.shared_group_id
    if not unchanged and not viewer.can_share_with(data.shared_group_id):
        raise ShareGroupNotJoinedError
    return NoteContent(
        title=NoteTitle(data.title),
        body=NoteBody(data.body),
        shared_group_id=data.shared_group_id,
    )
