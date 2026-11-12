class DomainError(Exception):
    """Base of the example context's domain exceptions. ``code`` is a stable key returned to the UI."""

    code = "item_error"


class ItemNotFoundError(DomainError):
    """No such item. **Items of other tenants are also reported as missing** (don't leak that they exist)."""

    code = "item_not_found"


class ItemValidationError(DomainError):
    code = "item_invalid"
