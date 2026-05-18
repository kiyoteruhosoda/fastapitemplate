class DomainException(Exception):
    pass


class ItemNotFoundError(DomainException):
    pass


class ItemValidationError(DomainException):
    pass
