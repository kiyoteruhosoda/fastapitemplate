"""``MachineActors`` の実装（振る舞う相手をテナントの席から引く）。

⚠ **ここで利用者を作らない。** 利用者が生まれるのは人がサインインしたとき・管理者が足したときだけで、
機械の設定で名簿を増やせないようにする。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.infrastructure.sign_in_directory import account_with_email


class SqlMachineActors:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def active_user_id(self, email: str) -> int | None:
        user = account_with_email(self._session, email, self._tenant_id)
        return user.id if user is not None and user.is_active else None


__all__ = ["SqlMachineActors"]
