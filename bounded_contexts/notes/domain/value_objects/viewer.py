"""The person handling notes (ADR-0078 §6).

``user_id`` comes from the token; ``group_ids`` **from the DB on the spot**. Memberships are not
put in the token: groups grow with the number of resources and would bloat the token (the same
problem as Azure cutting group claims off at 200).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Viewer:
    user_id: int
    #: Groups the user belongs to (within their own tenant only)
    group_ids: frozenset[int]

    def can_share_with(self, group_id: int | None) -> bool:
        """Whether it may be chosen as the share target: no sharing (``None``) or a group the user belongs to."""
        return group_id is None or group_id in self.group_ids


@dataclass(frozen=True)
class ShareTarget:
    """Groups that may be chosen as the share target."""

    group_id: int
    name: str
