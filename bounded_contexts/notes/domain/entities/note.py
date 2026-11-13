"""Shared note (sample for ADR-0078 §6).

The note itself answers "who can read this one, and who can change it". The token's scope
(``note:view`` / ``note:write``) only says whether the notes feature may be used; it knows nothing of which note.
"""

from dataclasses import dataclass

from bounded_contexts.notes.domain.value_objects.note_text import NoteBody, NoteTitle
from bounded_contexts.notes.domain.value_objects.viewer import Viewer


@dataclass(frozen=True)
class NoteContent:
    """What the writer decides (title, body, group shared with)."""

    title: NoteTitle
    body: NoteBody
    #: ``None`` means private. Pointing to a group lets its members read it too
    shared_group_id: int | None


@dataclass(frozen=True)
class Note:
    id: int
    owner_user_id: int
    content: NoteContent

    def owned_by(self, viewer: Viewer) -> bool:
        return self.owner_user_id == viewer.user_id

    def readable_by(self, viewer: Viewer) -> bool:
        """Readable by the owner or by a member of the group it is shared with.

        ⚠ **The list applies the same rule in SQL** (``SqlNoteRepository.find_readable``).
        Change one, change the other. ``tests/integration/api/test_notes.py`` fails if they diverge.
        """
        if self.owned_by(viewer):
            return True
        group_id = self.content.shared_group_id
        return group_id is not None and group_id in viewer.group_ids

    def changeable_by(self, viewer: Viewer) -> bool:
        """Only the owner may modify or delete. Those it is shared with can only read."""
        return self.owned_by(viewer)
