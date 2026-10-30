from dataclasses import dataclass

from bounded_contexts.notes.domain.exceptions import NoteValidationError

TITLE_MAX_LENGTH = 100
BODY_MAX_LENGTH = 4000


@dataclass(frozen=True)
class NoteTitle:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip() or len(self.value) > TITLE_MAX_LENGTH:
            raise NoteValidationError


@dataclass(frozen=True)
class NoteBody:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) > BODY_MAX_LENGTH:
            raise NoteValidationError
