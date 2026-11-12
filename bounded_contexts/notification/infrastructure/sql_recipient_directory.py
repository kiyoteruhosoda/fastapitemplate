"""SQLAlchemy implementation of ``IRecipientDirectory`` (users and groups are shared tables).

Only people and groups in the sender's tenant can be chosen as the audience (ADR-0079 §1).
Groups and users of other tenants are refused as not found.
"""

from __future__ import annotations

from bounded_contexts.notification.domain.exceptions import AudienceNotFoundError
from bounded_contexts.notification.domain.repositories.recipient_directory import IRecipientDirectory
from bounded_contexts.notification.domain.value_objects.audience import Audience, AudienceKind
from shared.infrastructure.tenant_scope import TenantMembers


class SqlRecipientDirectory(IRecipientDirectory):
    def __init__(self, members: TenantMembers) -> None:
        self._members = members

    def resolve(self, audience: Audience) -> list[int]:
        active = [u.id for u in self._members.users(active_only=True)]
        if audience.kind is AudienceKind.ALL:
            return active
        if audience.kind is AudienceKind.GROUP:
            group = self._members.group(audience.target_id or 0)
            if group is None:
                raise AudienceNotFoundError("group")
            members = {u.id for u in group.members}
            return [uid for uid in active if uid in members]
        if self._members.user(audience.target_id or 0) is None:
            raise AudienceNotFoundError("user")
        return [uid for uid in active if uid == audience.target_id]


__all__ = ["SqlRecipientDirectory"]
