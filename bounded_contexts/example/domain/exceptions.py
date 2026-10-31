class DomainError(Exception):
    """example コンテキストのドメイン例外の基底。``code`` は画面へ返す安定キー。"""

    code = "item_error"


class ItemNotFoundError(DomainError):
    """そのアイテムが無い。**ほかのテナントのものも「無い」と答える**（在ることを漏らさない）。"""

    code = "item_not_found"


class ItemValidationError(DomainError):
    code = "item_invalid"
