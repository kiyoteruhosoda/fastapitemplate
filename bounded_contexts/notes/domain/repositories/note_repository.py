from abc import ABC, abstractmethod

from bounded_contexts.notes.domain.entities.note import Note, NoteContent
from bounded_contexts.notes.domain.value_objects.viewer import ShareTarget, Viewer


class INoteRepository(ABC):
    """メモの置き場。テナントは実装のコンストラクタで受け取る（ADR-0079 §2）。

    ⚠ ``get`` は**読めるかどうかを見ない。** 確かめるのはユースケース（``Note.readable_by``）。
    """

    @abstractmethod
    def add(self, owner_user_id: int, content: NoteContent) -> Note: ...

    @abstractmethod
    def get(self, note_id: int) -> Note | None: ...

    @abstractmethod
    def find_readable(self, viewer: Viewer) -> list[Note]: ...

    @abstractmethod
    def replace(self, note: Note) -> None: ...

    @abstractmethod
    def remove(self, note_id: int) -> None: ...


class IGroupMembership(ABC):
    """利用者がどのグループに入っているか。**毎回 DB から引く**（ADR-0078 §6）。"""

    @abstractmethod
    def viewer(self, user_id: int) -> Viewer: ...

    @abstractmethod
    def share_targets(self, user_id: int) -> list[ShareTarget]: ...
