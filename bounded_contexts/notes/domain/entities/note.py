"""共有メモ（ADR-0070 の見本）。

「この 1 件を誰が読めて、誰が変えられるか」はメモ自身が答える。トークンの scope
（``note:view`` / ``note:write``）は「メモの機能を使えるか」までで、どのメモかは知らない。
"""

from dataclasses import dataclass

from bounded_contexts.notes.domain.value_objects.note_text import NoteBody, NoteTitle
from bounded_contexts.notes.domain.value_objects.viewer import Viewer


@dataclass(frozen=True)
class NoteContent:
    """書き手が決めるもの（題名・本文・共有先）。"""

    title: NoteTitle
    body: NoteBody
    #: ``None`` は自分だけ。グループを指すと、その一員も読める
    shared_group_id: int | None


@dataclass(frozen=True)
class Note:
    id: int
    owner_user_id: int
    content: NoteContent

    def owned_by(self, viewer: Viewer) -> bool:
        return self.owner_user_id == viewer.user_id

    def readable_by(self, viewer: Viewer) -> bool:
        """持ち主か、共有先のグループの一員なら読める。

        ⚠ **一覧は同じ決まりを SQL で書いている**（``SqlNoteRepository.find_readable``）。
        ここを変えたらあちらも変える。食い違いは ``tests/integration/api/test_notes.py`` が落とす。
        """
        if self.owned_by(viewer):
            return True
        group_id = self.content.shared_group_id
        return group_id is not None and group_id in viewer.group_ids

    def changeable_by(self, viewer: Viewer) -> bool:
        """書き換え・削除は持ち主だけ。共有された側は読むだけ。"""
        return self.owned_by(viewer)
