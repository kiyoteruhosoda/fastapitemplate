"""``IGroupMembership`` の SQLAlchemy 実装。

所属はトークンに載せず、**リクエストのたびにここで引く**（ADR-0070）。グループから
外されたら、次のリクエストからそのメモは読めなくなる（トークンの寿命を待たない）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from bounded_contexts.notes.domain.repositories.note_repository import IGroupMembership
from bounded_contexts.notes.domain.value_objects.viewer import ShareTarget, Viewer
from shared.infrastructure.models import UserGroup, user_group_members


class SqlGroupMembership(IGroupMembership):
    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def viewer(self, user_id: int) -> Viewer:
        return Viewer(user_id=user_id, group_ids=frozenset(t.group_id for t in self.share_targets(user_id)))

    def share_targets(self, user_id: int) -> list[ShareTarget]:
        rows = self._session.execute(
            select(UserGroup.id, UserGroup.name)
            .join(user_group_members, user_group_members.c.group_id == UserGroup.id)
            .where(user_group_members.c.user_id == user_id, UserGroup.tenant_id == self._tenant_id)
            .order_by(UserGroup.name)
        ).all()
        return [ShareTarget(group_id=group_id, name=name) for group_id, name in rows]
