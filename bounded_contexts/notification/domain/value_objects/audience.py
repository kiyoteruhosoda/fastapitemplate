from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from bounded_contexts.notification.domain.exceptions import NotificationValidationError


class AudienceKind(StrEnum):
    """Audience kind. The values are stable keys stored in the DB and exposed in the API; don't change them."""

    ALL = "all"
    GROUP = "group"
    USER = "user"


@dataclass(frozen=True)
class Audience:
    """Whom to send to. ``ALL`` has no target; ``GROUP`` / ``USER`` carry the target's ID."""

    kind: AudienceKind
    target_id: int | None = None

    def __post_init__(self) -> None:
        if self.kind is AudienceKind.ALL:
            if self.target_id is not None:
                raise NotificationValidationError("audience_target_not_allowed")
        elif self.target_id is None:
            raise NotificationValidationError("audience_target_required")

    @classmethod
    def everyone(cls) -> Audience:
        return cls(AudienceKind.ALL)

    @classmethod
    def group(cls, group_id: int) -> Audience:
        return cls(AudienceKind.GROUP, group_id)

    @classmethod
    def user(cls, user_id: int) -> Audience:
        return cls(AudienceKind.USER, user_id)
