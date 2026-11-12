"""Binding between an external IdP account and a user of this app.

Keyed by ``(issuer, subject)``. Email can change, so it isn't a key.
No uniqueness constraint on the user side, so one user can have multiple IdPs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FederatedIdentity:
    issuer: str
    subject: str
    user_id: int
    #: When it was bound. Set only when a stored row is loaded (for display).
    linked_at: datetime | None = None
    #: When the user last signed in via SSO. Set only when a stored row is loaded.
    #: Used by the periodic reconciliation to decide "which login a revocation targets" (ADR-0077 §7).
    last_login_at: datetime | None = None


__all__ = ["FederatedIdentity"]
