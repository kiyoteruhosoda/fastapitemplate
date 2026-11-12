"""Matching the requested authentication strength (``acr_values``) against the returned ``acr``.

**If you request it, verify it; otherwise don't request it** (ADR-0076 §3 decision 1). Merely
sending ``acr_values`` guarantees nothing — one typo in the IdP-side policy drops the condition
and single-factor logins silently pass. The only way for the RP to notice is to match the
returned ``acr`` against the request.

⚠ **``amr`` is not used.** RFC 8176 ``amr`` lists the methods used, not a strength. Via an
external IdP (``fed``) the IdP itself doesn't know what was used beyond it, so whether it was
multi-factor can't be read from the values.
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAcrNotSatisfiedError,
)


@dataclass(frozen=True)
class RequestedAuthenticationContext:
    #: Candidate ``acr`` values to require. **Empty = none required** (default).
    values: tuple[str, ...] = ()

    @property
    def is_requested(self) -> bool:
        return bool(self.values)

    def ensure_satisfied(self, acr: object) -> None:
        """Check that the returned ``acr`` matches one of the requested values.

        ⚠ **Also refuse when no ``acr`` comes back.** It was requested but not assured, so it must
        not pass. Derived apps connecting to an IdP without reserved values work as before by not
        requesting at all (empty ``values``).
        """
        if not self.is_requested:
            return
        if not isinstance(acr, str) or acr not in self.values:
            raise SsoAcrNotSatisfiedError


__all__ = ["RequestedAuthenticationContext"]
