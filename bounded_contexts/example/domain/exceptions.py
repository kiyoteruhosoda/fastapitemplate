class DomainError(Exception):
    pass


class ItemNotFoundError(DomainError):
    pass


class ItemValidationError(DomainError):
    pass
