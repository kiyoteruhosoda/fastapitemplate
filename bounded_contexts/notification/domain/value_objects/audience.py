from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from bounded_contexts.notification.domain.exceptions import NotificationValidationError


class AudienceKind(StrEnum):
    """宛先の種類。値が DB と API に出る安定キーなので変えない。"""

    ALL = "all"
    GROUP = "group"
    USER = "user"


@dataclass(frozen=True)
class Audience:
    """誰に送るか。``ALL`` は相手を持たず、``GROUP`` / ``USER`` は相手の ID を持つ。"""

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
