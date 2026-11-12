"""One session of this app that started via the IdP (ADR-0077 §3).

The address (:class:`FederatedSession`) plus **when it started**. Logout records work as
"invalidate sessions started before this time", so the time is needed.

⚠ **It's when the session started, not when the token was issued.** Renewing it on each
refresh would let **a single refresh slip past the stop** (the ``iat`` of a refreshed
token is always after the stop).

⚠ **The token's ``iat`` can't substitute.** ``iat`` only has second precision, so it would
catch a user who signed in again within the same second right after the stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)


@dataclass(frozen=True)
class FederatedLogin:
    session: FederatedSession
    started_at: datetime


__all__ = ["FederatedLogin"]
