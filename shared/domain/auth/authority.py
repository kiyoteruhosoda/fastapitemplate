"""Rules for granting and revoking permissions (ADR-0078 §4).

Adding/removing roles, changing a role's content and suspending users are themselves operations
that "move permissions". This module holds only the pure rules that decide whether such an
operation **stays within the operator's own permissions** (no DB or framework dependency).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

from shared.domain.auth.master_data import ROLE_PERMISSIONS, SYSTEM_PERMISSIONS, SYSTEM_ROLES

# The "administration core". Anyone holding both of these can redistribute every other permission.
# Changes that would leave zero active users holding them are rejected.
ADMINISTRATION_CORE: tuple[str, ...] = ("user:manage", "role:manage")


def beyond(actor: Collection[str], required: Iterable[str]) -> frozenset[str]:
    """Permissions in ``required`` that ``actor`` does not hold. Empty means within scope.

    **Permissions one does not hold can be neither granted nor revoked.** Not checking on grant
    opens an escalation path (someone with only ``user:manage`` gives themselves ``owner``); not
    checking on revoke lets one disarm a superior.
    """
    return frozenset(code for code in required if code not in actor)


def changed(before: Iterable[str], after: Iterable[str]) -> frozenset[str]:
    """What was added or removed (symmetric difference). Either direction moves permissions."""
    return frozenset(before) ^ frozenset(after)


_SYSTEM_SEAT_PERMISSIONS = frozenset(code for role in SYSTEM_ROLES for code in ROLE_PERMISSIONS[role])


def within_the_seat(in_tenant: bool, granted: Iterable[str]) -> frozenset[str]:
    """Keep only the permissions effective for the seat (inside or outside the tenants; ADR-0079 §1).

    **System administrator and tenant administrator are never combined.** Even if roles are
    assigned by mistake, global permissions do not apply to tenant users, and inside permissions do
    not apply to users outside the tenants. This doubles the gate on adding/removing roles
    (``TenantMembers.roles``).
    """
    codes = frozenset(granted)
    if in_tenant:
        return codes - frozenset(SYSTEM_PERMISSIONS)
    return codes & _SYSTEM_SEAT_PERMISSIONS


__all__ = ["ADMINISTRATION_CORE", "beyond", "changed", "within_the_seat"]
