"""A user as claimed by the IdP (result of mapping the claims).

``subject`` is the IdP's immutable identifier, and accounts are bound by it.
Email can change, so it is **not a binding key** (used only as a clue to find an existing
local account the first time. ADR-0077 §1).

⚠ **Not being a key, it may be absent** (ADR-0077 §6). Some IdPs don't provide it
— **rejecting in that case was a leftover from when it was a key.**
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedUser:
    subject: str
    #: ⚠ **Optional** (ADR-0077 §6). The binding key is ``subject``, so already bound
    #: parties can sign in without an email. It is only needed
    #: **when merging by email the first time** and **when creating a user**.
    email: str | None
    username: str
    email_verified: bool = False

    @property
    def email_domain(self) -> str:
        _, _, domain = (self.email or "").rpartition("@")
        return domain.lower()


__all__ = ["FederatedUser"]
