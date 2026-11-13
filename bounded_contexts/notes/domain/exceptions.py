class NoteError(Exception):
    """Base of the notes context's domain exceptions. ``code`` is a stable key returned to the UI."""

    code = "note_error"


class NoteNotFoundError(NoteError):
    """No such note. **A note the caller cannot read is also reported as missing**
    (don't leak that it exists; ADR-0078 §6)."""

    code = "note_not_found"


class NoteNotOwnedError(NoteError):
    """Readable but not changeable (tried to modify a note shared with the caller)."""

    code = "note_not_owned"


class ShareGroupNotJoinedError(NoteError):
    """Tried to share with a group the caller is not a member of."""

    code = "share_group_not_joined"


class NoteValidationError(NoteError):
    """Title or body breaks the rules."""

    code = "invalid_note"
