"""Gateway that fetches assay's roster (ADR-0077 §7. Implemented in Infrastructure).

⚠ **Don't represent "couldn't fetch" as "empty".** Implementations report failure with
:class:`~bounded_contexts.identity_federation.domain.exceptions.IdentityProviderUnavailableError`
and the caller skips the reconciliation itself — if it were indistinguishable from empty, everyone
would be stopped just because assay is unwell.

⚠ When **this service account is not yet bound as the app's identity**, it is reported separately
:class:`~bounded_contexts.identity_federation.domain.exceptions.MachineNotBoundToApplicationError`
(not a fault; waiting for setup). Nothing is changed in this case either.
"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.value_objects.roster import Roster


class RosterGateway(Protocol):
    def fetch(self, *, subjects: tuple[str, ...]) -> Roster:
        """Fetch the status of each of *subjects* (assay decides whose roster from the calling service account).

        ⚠ **Ask by name.** Only this form returns ``unknown`` (= not there); listing candidates
        can't tell "deleted".
        """


__all__ = ["RosterGateway"]
