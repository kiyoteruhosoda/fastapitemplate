"""共有メモのユースケース。

どの操作も、最初に「誰が」を :class:`IGroupMembership` で組み立てる（所属は毎回 DB から）。
"""

from bounded_contexts.notes.application.dto.note_dto import NoteDTO, NoteInput, ShareTargetDTO
from bounded_contexts.notes.application.use_cases.note_access import (
    changeable_note,
    content_for,
    readable_note,
)
from bounded_contexts.notes.domain.entities.note import Note
from bounded_contexts.notes.domain.repositories.note_repository import IGroupMembership, INoteRepository


class NoteBook:
    def __init__(self, notes: INoteRepository, membership: IGroupMembership) -> None:
        self._notes = notes
        self._membership = membership

    def list_readable(self, user_id: int) -> list[NoteDTO]:
        viewer = self._membership.viewer(user_id)
        return [NoteDTO.of(note, viewer) for note in self._notes.find_readable(viewer)]

    def get(self, user_id: int, note_id: int) -> NoteDTO:
        viewer = self._membership.viewer(user_id)
        return NoteDTO.of(readable_note(self._notes, viewer, note_id), viewer)

    def create(self, user_id: int, data: NoteInput) -> NoteDTO:
        viewer = self._membership.viewer(user_id)
        note = self._notes.add(viewer.user_id, content_for(viewer, data))
        return NoteDTO.of(note, viewer)

    def update(self, user_id: int, note_id: int, data: NoteInput) -> NoteDTO:
        viewer = self._membership.viewer(user_id)
        current = changeable_note(self._notes, viewer, note_id)
        updated = Note(id=current.id, owner_user_id=current.owner_user_id, content=content_for(viewer, data, current))
        self._notes.replace(updated)
        return NoteDTO.of(updated, viewer)

    def delete(self, user_id: int, note_id: int) -> None:
        viewer = self._membership.viewer(user_id)
        self._notes.remove(changeable_note(self._notes, viewer, note_id).id)

    def share_targets(self, user_id: int) -> list[ShareTargetDTO]:
        return [ShareTargetDTO(id=t.group_id, name=t.name) for t in self._membership.share_targets(user_id)]
