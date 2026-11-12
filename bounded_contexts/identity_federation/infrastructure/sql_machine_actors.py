"""Implementation of ``MachineActors`` (looks up the user to act as from the tenant's seats).

⚠ **Users are not created here.** Users only come into being when a person signs in or an admin adds them,
so machine settings can't grow the roster.
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
