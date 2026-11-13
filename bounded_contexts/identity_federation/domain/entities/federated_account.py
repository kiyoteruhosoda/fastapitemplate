"""A user of this app as seen from SSO.

Not the ``shared`` ``User`` model itself; it holds only the fields identity federation needs.
A boundary to keep Domain from touching SQLAlchemy models; exchanges with the real entity
go through :class:`FederatedUserDirectory` in
``domain/repositories/federated_user_directory.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedAccount:
    user_id: int
    email: str
    is_active: bool
    roles: tuple[str, ...] = ()
    #: A designated seat nobody has entered yet (no password, IdP binding or passkey. ADR-0079 §5)
    awaiting_owner: bool = False


@dataclass(frozen=True)
class NewFederatedAccount:
    """A user about to be created (automatic provisioning on first login)."""

    email: str
    username: str
    roles: tuple[str, ...] = ()


__all__ = ["FederatedAccount", "NewFederatedAccount"]
