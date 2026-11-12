"""Roles given to users who signed in via the IdP.

Authorization itself uses scopes (permission codes) (CLAUDE.md "Permission management"). This only
decides **which roles to give**; scopes are already determined as the permissions roles hold.

⚠ **Not derived from groups** (ADR-0077 §6 / idp ADR-0049 G7). Our own idp (assay) doesn't
issue a ``groups`` claim, so it was **a setting that existed but never took effect**.
idp ADR-0049 decides as I6 that "**permissions are held by the RP; the IdP doesn't hand them
out**", so removing the deriving side is the right thing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleAssignment:
    """Default roles given to users who signed in via the IdP.

    If ``sync_on_login`` is true they are re-applied on every login. ⚠ **Only the default roles
    are re-applied, so roles added on the admin screen disappear on every login.** Set it false
    if managing via the admin screen (default is false).
    """

    default_roles: tuple[str, ...] = ()
    sync_on_login: bool = False

    @classmethod
    def from_rules(cls, defaults: Sequence[str], *, sync_on_login: bool) -> RoleAssignment:
        return cls(
            default_roles=tuple(dict.fromkeys(role for role in defaults if role)),
            sync_on_login=sync_on_login,
        )

    def roles(self) -> tuple[str, ...]:
        """Roles to give."""
        return self.default_roles


__all__ = ["RoleAssignment"]
