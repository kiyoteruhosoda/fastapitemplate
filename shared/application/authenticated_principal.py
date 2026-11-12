"""Authenticated principal (the verification result passed to the Presentation layer).

Authorization decisions are made only by :meth:`can` (scope based; see "Permissions" in CLAUDE.md).

``active_role`` is held only to show and switch "which role is in use now" (ADR-0078 §1).
**Do not branch authorization on it**: the active role is already reflected in the narrowed
:attr:`permissions`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: int
    email: str
    username: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    # None = operating with all roles (the union of held permissions)
    active_role: str | None = None
    #: When the person last **actually** signed in (UTC, aware; ADR-0076 §10). Not renewed by
    #: refreshes or role switches. ``None`` means unknown (tokens older than this mechanism).
    authenticated_at: datetime | None = None
    #: The tenant the user belongs to (ADR-0079 §1). ``None`` means no tenant (system administrator).
    #: ⚠ **Do not read ``None`` as "all tenants".** No tenant's content is visible.
    tenant_id: int | None = None
    #: For a token issued by the machine endpoint, the ``client_id`` of the machine (ADR-0087).
    #: ``None`` for a human sign-in.
    #: ⚠ Machine principals pass only scope-protected endpoints (:func:`get_current_principal` refuses).
    machine_client_id: str | None = None
    #: Whether this sign-in can only reach the enrollment endpoints until 2FA is set up (ADR-0093).
    two_factor_setup_required: bool = False

    @property
    def is_machine(self) -> bool:
        return self.machine_client_id is not None

    @property
    def id_hash(self) -> str:
        """User identifier for logs (a hash, to keep PII out)."""
        return hashlib.sha256(str(self.user_id).encode()).hexdigest()[:16]

    def can(self, *codes: str) -> bool:
        """Whether **all** the given permission codes are held."""
        return all(code in self.permissions for code in codes)


__all__ = ["AuthenticatedPrincipal"]
