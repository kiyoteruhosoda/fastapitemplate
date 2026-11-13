"""Wiring for the periodic reconciliation (ADR-0077 §7).

Connects the use case (Application) with the implementations (Infrastructure).
Infrastructure can't import Application, so the outermost layer does the wiring.

**Settings are read on every run.** Once SSO is enabled and ``MACHINE_CLIENT_ID`` is set, it takes effect
from the next cycle.

⚠ **Don't decide whether to run by the app's identity.** If SSO is usable and the service account has a `client_id`,
it asks every cycle; until assay binds this service account as the app's identity, a 403 comes back
— that is logged as "not yet bound" in one info line, and it ends without changing anything.

⚠ **Opens its own session.** It runs outside the request flow, so the ``get_db`` session
(opened and closed per request) can't be used.
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from bounded_contexts.identity_federation.application.use_cases.reconcile_federated_users import (
    ReconcileFederatedUsers,
    ReconciliationOutcome,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.services.roster_gateway import (
    RosterGateway,
)
from bounded_contexts.identity_federation.infrastructure.httpx_roster_gateway import (
    HttpxRosterGateway,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from bounded_contexts.identity_federation.presentation import dependencies
from shared.kernel.database.db import get_engine
from shared.kernel.scheduling import start_interval_worker
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

WORKER_NAME = "sso-reconciliation"

# Reconciliation interval. ⚠ **Not a setting.** The interval is read only once at startup, so exposing it on
# screen would make "a setting that has no effect when changed". The main path for catching suspended users
# quickly is the receiver (ADR-0077 §3); this is the second tier that catches misses, so 1 hour is enough.
RECONCILE_INTERVAL_SECONDS = 60 * 60

#: One per process. ⚠ **The token is reused across cycles**, so don't create one per call.
_ROSTER: RosterGateway = HttpxRosterGateway()

#: Failures where we skipped without changing anything. ⚠ **Don't read "could not fetch" as "empty"**
#: (ADR-0077 §7 decision 2).
_SKIPPABLE = (IdentityProviderUnavailableError, SsoNotConfiguredError)


def reconcile_federated_users_once(roster: RosterGateway | None = None) -> None:
    """Reconcile once according to the current settings.

    ⚠ **If assay can't be asked, end without changing anything** (don't mix "empty" and "unfetchable").
    """
    if not settings.machine_client_id or not settings.oidc_enabled:
        # If configured not to reconcile, don't even open a session.
        return
    session = sessionmaker(bind=get_engine())()
    try:
        # Only the ``OIDC_ISSUER`` tenant is reconciled (a service account is needed per assay tenant,
        # so the single ``MACHINE_CLIENT_ID`` can ask about one tenant. ADR-0079 §4)
        provider = dependencies.provider_issuing(session, settings.oidc_issuer)
        if provider is None or not provider.is_usable:
            return
        outcome = _reconcile(session, provider.issuer, roster or _ROSTER)
    finally:
        session.close()
    if outcome is not None:
        logger.info(
            "sso_reconciliation_finished",
            extra={
                "checked": outcome.checked,
                "revoked": outcome.revoked,
                "unlinked": outcome.unlinked,
                "held_back": outcome.held_back,
            },
        )


def _reconcile(session: Session, issuer: str, roster: RosterGateway) -> ReconciliationOutcome | None:
    """Reconcile and commit. If skipped, roll back and return ``None``."""
    try:
        outcome = ReconcileFederatedUsers(
            # ⚠ Look up by the issuer from **the same source** as when binding. If the spelling is off
            #   by one character, nothing matches and it ends as "all fine" without checking anything.
            issuer=issuer,
            identities=SqlFederatedIdentityRepository(session),
            revocations=SqlSessionRevocationRepository(session),
            roster=roster,
            keep_for_seconds=settings.refresh_token_expires_seconds,
        ).execute()
        session.commit()
    except MachineNotBoundToApplicationError:
        session.rollback()
        # ⚠ Waiting for setup, not a fault. It comes hourly until bound, so not a warning.
        logger.info("sso_reconciliation_not_bound")
        return None
    except _SKIPPABLE as error:
        session.rollback()
        logger.warning("sso_reconciliation_skipped", extra={"reason": type(error).__name__})
        return None
    except IntegrityError:
        # Another worker wrote the same revocation in the same cycle
        # (`jti` is deterministic, so the content is the same).
        session.rollback()
        logger.info("sso_reconciliation_raced")
        return None
    return outcome


def start_sso_reconciliation_worker() -> None:
    """Start the periodic reconciliation (called from process startup)."""
    start_interval_worker(WORKER_NAME, reconcile_federated_users_once, RECONCILE_INTERVAL_SECONDS)


__all__ = [
    "RECONCILE_INTERVAL_SECONDS",
    "WORKER_NAME",
    "reconcile_federated_users_once",
    "start_sso_reconciliation_worker",
]
