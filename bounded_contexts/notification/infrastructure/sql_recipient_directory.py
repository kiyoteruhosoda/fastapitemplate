"""``IRecipientDirectory`` の SQLAlchemy 実装（利用者・グループは shared のテーブル）。"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bounded_contexts.notification.domain.exceptions import AudienceNotFoundError
from bounded_contexts.notification.domain.repositories.recipient_directory import IRecipientDirectory
from bounded_contexts.notification.domain.value_objects.audience import Audience, AudienceKind
from shared.infrastructure.models import User, UserGroup, user_group_members


class SqlRecipientDirectory(IRecipientDirectory):
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, audience: Audience) -> list[int]:
        active = sa.select(User.id).where(User.is_active.is_(True))
        if audience.kind is AudienceKind.ALL:
            query = active
        elif audience.kind is AudienceKind.GROUP:
            if self._session.get(UserGroup, audience.target_id) is None:
                raise AudienceNotFoundError("group")
            query = active.join(user_group_members, user_group_members.c.user_id == User.id).where(
                user_group_members.c.group_id == audience.target_id
            )
        else:
            if self._session.get(User, audience.target_id) is None:
                raise AudienceNotFoundError("user")
            query = active.where(User.id == audience.target_id)
        return list(self._session.scalars(query.order_by(User.id)).all())


__all__ = ["SqlRecipientDirectory"]
