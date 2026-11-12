"""Round-trip state of an authorization request (``state`` / ``nonce`` / PKCE ``code_verifier`` / return target).

Bundles the values needed **only while** redirecting away to the IdP and coming back.
No copy is kept server-side; it is **entrusted to the browser in a tamper-proof form** (ADR-0077 §1).
Signing and cookie handling belong to the Presentation layer (``presentation.transaction_cookie``);
this only holds the values and the judgement "is this return from the same round trip".

⚠ **It holds `code_verifier`, so it is a credential.** The cookie is ``HttpOnly``
(JavaScript must not be able to read it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest

from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)


@dataclass(frozen=True)
class LoginTransaction:
    state: str
    nonce: str
    code_verifier: str
    redirect_to: str = "/"
    #: What this round trip was started for (ADR-0077 §5).
    purpose: TransactionPurpose = TransactionPurpose.LOGIN
    #: The user who started the linking round trip. For a renewal round trip, the user of the continued
    #: login (``None`` if unknown).
    #: ``None`` for a login round trip.
    #:
    #: ⚠ **Exists to be matched against the session on return.** Without it, a browser whose user
    #:   switched mid-round-trip would bind **to that other person's account**.
    user_id: int | None = None
    #: Issuer sent out to (= tenant. ADR-0079 §1). The return is received with this issuer's client.
    #:
    #: ⚠ **Don't re-decide from the query on return.** If the tenant could be re-chosen via URL, a round
    #:   trip started in one tenant could be completed as a user of another tenant.
    issuer: str = ""
    #: A silent attempt round trip (``prompt=none``. ADR-0077 §9).
    #:
    #: ⚠ **Exists to decide how to handle "not signed in" on return.** It was only an attempt, so it's
    #:   not a failure; return to the login screen without an error.
    silent: bool = False
    #: Active role of the continued login (renewal round trip only. ADR-0104). Carried over on return if still held
    active_role: str | None = None
    #: When the person last actually signed in, for the continued login (renewal round trip only.
    #: ADR-0076 §10, ADR-0104).
    #:
    #: ⚠ **Continuing is not signing in again.** Without carrying it over, it becomes "just signed in" every 5 min.
    authenticated_at: datetime | None = None
    #: Whether the continued login used a passkey (renewal round trip only. ADR-0093)
    signed_in_with_passkey: bool = False

    def is_for(self, issuer: str) -> bool:
        """Whether this round trip was sent out to that issuer."""
        return bool(self.issuer) and compare_digest(self.issuer, issuer)

    def matches(self, state: str) -> bool:
        """Whether the returned ``state`` is the one sent out in this round trip.

        **Without the cookie this judgement can't even be made** (the caller can't restore the
        round-trip state). Unlike keeping a copy in a table, a party that only knows ``state``
        can't complete the return — even if a victim is tricked into an authorization request started
        by an attacker, the victim's browser has no matching cookie (login CSRF).

        Compared with :func:`hmac.compare_digest` (so the number of matching characters can't be
        guessed from response time).
        """
        return bool(state) and compare_digest(self.state, state)

    def belongs_to(self, user_id: int) -> bool:
        """Whether the user who started the linking round trip is this currently signed-in user."""
        return self.user_id is not None and self.user_id == user_id


__all__ = ["LoginTransaction"]
