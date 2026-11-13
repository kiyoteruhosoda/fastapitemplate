from abc import ABC, abstractmethod

from bounded_contexts.notes.domain.entities.note import Note, NoteContent
from bounded_contexts.notes.domain.value_objects.viewer import ShareTarget, Viewer


class INoteRepository(ABC):
    """Store of notes. The implementation takes the tenant in its constructor (ADR-0079 §2).

    ⚠ ``get`` **does not check readability.** The use case checks it (``Note.readable_by``).
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
    """Which groups a user belongs to. **Looked up from the DB every time** (ADR-0078 §6)."""

    @abstractmethod
    def viewer(self, user_id: int) -> Viewer: ...

    @abstractmethod
    def share_targets(self, user_id: int) -> list[ShareTarget]: ...
