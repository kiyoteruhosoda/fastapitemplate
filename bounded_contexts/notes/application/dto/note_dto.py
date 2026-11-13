from dataclasses import dataclass

from bounded_contexts.notes.domain.entities.note import Note
from bounded_contexts.notes.domain.value_objects.viewer import Viewer


@dataclass(frozen=True)
class NoteInput:
    """Title, body and share target received from the UI (validated plain values)."""

    title: str
    body: str
    shared_group_id: int | None


@dataclass(frozen=True)
class NoteDTO:
    id: int
    title: str
    body: str
    shared_group_id: int | None
    #: Whether it is the caller's own note (for display)
    mine: bool
    #: Whether this person may modify/delete this note (is the owner). **The UI combines it with the scope**
    #: (the ``note:write`` scope alone does not say which note; ADR-0078 §6)
    can_change: bool

    @classmethod
    def of(cls, note: Note, viewer: Viewer) -> NoteDTO:
        return cls(
            id=note.id,
            title=note.content.title.value,
            body=note.content.body.value,
            shared_group_id=note.content.shared_group_id,
            mine=note.owned_by(viewer),
            can_change=note.changeable_by(viewer),
        )


@dataclass(frozen=True)
class ShareTargetDTO:
    id: int
    name: str
