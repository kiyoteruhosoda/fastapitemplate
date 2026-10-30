from dataclasses import dataclass

from bounded_contexts.notes.domain.entities.note import Note
from bounded_contexts.notes.domain.value_objects.viewer import Viewer


@dataclass(frozen=True)
class NoteInput:
    """画面から受け取る題名・本文・共有先（検証済みの素の値）。"""

    title: str
    body: str
    shared_group_id: int | None


@dataclass(frozen=True)
class NoteDTO:
    id: int
    title: str
    body: str
    shared_group_id: int | None
    #: 自分のメモか（表示用）
    mine: bool
    #: この人がこの 1 件を書き換え・削除できるか（持ち主か）。**画面は scope と合わせて出し分ける**
    #: （scope の ``note:write`` だけでは、どのメモかが分からない。ADR-0078 §6）
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
