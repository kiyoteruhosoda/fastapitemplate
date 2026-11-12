"""Ask assay again and stop SSO sessions of people who can no longer use it (periodic
reconciliation. ADR-0077 §7).

The second tier, catching what the receiver (ADR-0077 §3) missed. What it stops is the same as
the receiver — **only sessions started via SSO**; the user itself (local password, passkeys)
is untouched. This template intentionally keeps local accounts (ADR-0076 §7).

⚠ **Do nothing when the lookup fails.** Don't mix "can't fetch the roster" with "the roster
is empty" — mixing them would stop everyone just because assay is unwell. On failure
:class:`~bounded_contexts.identity_federation.domain.exceptions.IdentityProviderUnavailableError`
is raised and this job ends without changing anything.

⚠ **Written so that any number of runs gives the same result.** Periodic jobs run
concurrently, one per worker (ADR-0075 §3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.services.roster_gateway import (
    RosterGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.roster import (
    Roster,
    RosterState,
)
from shared.kernel.timestamps import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationOutcome:
    """What happened in one reconciliation (counts for logging and tests)."""

    checked: int = 0
    #: Number newly revoked. ⚠ People already revoked in a previous cycle aren't counted (same row isn't written).
    revoked: int = 0
    unlinked: int = 0
    #: ⚠ Whether it **was skipped because everyone came back `unknown`** (decision 3). When true nothing changed.
    held_back: bool = False


@dataclass(frozen=True)
class ReconcileFederatedUsers:
    issuer: str
    identities: FederatedIdentityRepository
    revocations: SessionRevocationRepository
    roster: RosterGateway
    #: Minimum seconds to keep revocation records. Pass **the refresh token lifetime** (same as the receiver.
    #: ADR-0102).
    keep_for_seconds: int

    def execute(self) -> ReconciliationOutcome:
        links = list(self.identities.list_for_issuer(self.issuer))
        if not links:
            return ReconciliationOutcome()
        # ⚠ Ask by name. A candidate list can't tell "not there anymore (deleted)".
        answers = self.roster.fetch(subjects=tuple(link.subject for link in links))
        outcome = ReconciliationOutcome(checked=len(links))
        if _everyone_is_unknown(links, answers):
            # ⚠ A tenant mix-up or app reassignment also looks like this. Bindings can only be recreated
            #   by the person themselves (ADR-0077 §5), so stop before removing everyone's.
            logger.warning("sso_reconciliation_everyone_unknown", extra={"checked": len(links)})
            return replace(outcome, held_back=True)
        now = utcnow()
        for link in links:
            outcome = self._apply(link, answers.state_of(link.subject), now, outcome)
        return outcome

    def _apply(
        self,
        link: FederatedIdentity,
        state: RosterState,
        now: datetime,
        outcome: ReconciliationOutcome,
    ) -> ReconciliationOutcome:
        """Apply one person's result. ⚠ **Also return the untouched side explicitly.**"""
        if not state.ends_sessions:
            return outcome
        revocation = SessionRevocation.after_reconciliation(
            link,
            now=now,
            keep_for_seconds=self.keep_for_seconds,
        )
        if self.revocations.record(revocation):
            logger.info("sso_sessions_revoked_by_reconciliation", extra={"user_id": link.user_id})
            outcome = replace(outcome, revoked=outcome.revoked + 1)
        if not state.drops_the_link:
            return outcome
        # Not there = the bound party no longer exists. Keeping the row would connect to someone else if
        # the same `sub` were reused for another person (promised not to be reused, but no reason to keep it).
        # ⚠ Revocation records apply to `(issuer, sub)`, not the binding, so they remain after removal.
        self.identities.unlink(link)
        logger.info("sso_identity_unlinked_by_reconciliation", extra={"user_id": link.user_id})
        return replace(outcome, unlinked=outcome.unlinked + 1)


def _everyone_is_unknown(links: list[FederatedIdentity], answers: Roster) -> bool:
    """Whether there are 2+ bindings and everyone came back `unknown` (ADR-0077 §7 decision 3).

    With only one, "that one person was deleted" can't be told apart, so it is handled normally.
    """
    if len(links) < 2:
        return False
    return all(answers.state_of(link.subject) is RosterState.UNKNOWN for link in links)


__all__ = ["ReconcileFederatedUsers", "ReconciliationOutcome"]
