class NoteError(Exception):
    """notes コンテキストのドメイン例外の基底。``code`` は画面へ返す安定キー。"""

    code = "note_error"


class NoteNotFoundError(NoteError):
    """そのメモが無い。**読めないメモも「無い」と答える**（在ることを漏らさない。ADR-0078 §6）。"""

    code = "note_not_found"


class NoteNotOwnedError(NoteError):
    """読めるが変えられない（共有されたメモを書き換えようとした）。"""

    code = "note_not_owned"


class ShareGroupNotJoinedError(NoteError):
    """自分が入っていないグループへ共有しようとした。"""

    code = "share_group_not_joined"


class NoteValidationError(NoteError):
    """題名・本文が決まりに合わない。"""

    code = "invalid_note"
