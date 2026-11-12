"""What a new token carries over from the previous session.

Paths that reissue tokens (refresh, role switch, password change) pass on the previous session's
**role** (ADR-0078 §1), **IdP session** (ADR-0077 §3) and **time of the last actual sign-in**
(ADR-0076 §10) without dropping any. Dropping even one makes the token something else:
IdP termination stops working, one can appear "just signed in again" without doing so, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)


@dataclass(frozen=True)
class SessionCarryOver:
    """The default (nothing passed) means "just came in through an entrance"."""

    active_role: str | None = None
    federated_login: FederatedLogin | None = None
    #: ``None`` means "signed in just now". Only entrances (password, passkey, SSO) may pass it
    authenticated_at: datetime | None = None
    #: Record of the continued login (ADR-0091). ``None`` is a new login, which creates one row
    refresh_session_id: str | None = None
    #: Refresh token presented at the refresh endpoint. Reset the cookie only if it is the current one
    presented_jti: str | None = None
    #: Whether the login used a passkey. A passkey satisfies two factors on its own (ADR-0093)
    signed_in_with_passkey: bool = False
    #: Create a new row but inherit the lifetime from this record (password change; ADR-0101)
    lifetime_from_session_id: str | None = None


#: A session that just came in through an entrance
FRESH_SIGN_IN = SessionCarryOver()

__all__ = ["FRESH_SIGN_IN", "SessionCarryOver"]
