"""Address of one IdP-side login session (ADR-0077 §3).

``(issuer, subject)`` is "who", and ``session_id`` (the ID token's ``sid``) is
"which login". Logout propagation arrives addressed by this triple — if ``sid`` is
known, **only that device's session** can be dropped.

``session_id`` is ``None`` in two cases.

- **The IdP doesn't provide ``sid``.** Then revocation is only possible per user.
- **The logout notice has no ``sid``** (the whole user was stopped). Then
    **all** of that user's sessions are dropped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedSession:
    issuer: str
    subject: str
    session_id: str | None = None


__all__ = ["FederatedSession"]
