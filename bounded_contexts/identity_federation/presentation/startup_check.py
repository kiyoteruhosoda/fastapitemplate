"""Check the SSO settings once at startup and log the outcome.

⚠ **The private key is first read only when signing.** Even with wrong permissions, startup
and the settings-screen check pass, and it fails only at the moment a user returns from the
IdP (ADR-0077 §1). Reading it once here lets us notice right after a deploy.

Setting values themselves are not logged (CLAUDE.md "Logging"). Only "usable / unusable"
and, if unusable, the category.
"""

from __future__ import annotations

import logging

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.infrastructure.client_assertion import (
    read_private_key,
)
from bounded_contexts.identity_federation.presentation.dependencies import (
    client_credential,
)
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)


def report_sso_configuration() -> None:
    """If configured to use SSO, check that it can actually start."""
    if not settings.oidc_enabled:
        return
    # The connection (issuer and client ID) is per tenant; only app-wide credentials are checked here (ADR-0079 §4)
    credential = client_credential()
    if not credential.is_complete or not settings.oidc_redirect_uri:
        # A mismatch of "meant to enable it but it's disabled" can only be noticed here.
        logger.error("sso_disabled_by_configuration")
        return
    if not credential.uses_private_key:
        logger.info("sso_ready")
        return
    try:
        read_private_key(credential)
    except SsoNotConfiguredError:
        # read_private_key has already logged the reason (exception type only).
        logger.error("sso_private_key_unreadable")
        return
    logger.info("sso_ready")


def report_machine_entrance() -> None:
    """Log whether the machine endpoint is open (ADR-0082 §2 decision 4, ADR-0087).

    ⚠ **If the allowlist exists but the audience is empty, the endpoint is closed.** Machines all get 401,
    so make it noticeable here.
    """
    if not settings.machine_clients:
        return
    if not settings.machine_audience:
        logger.error("machine_entrance_closed_audience_missing")
        return
    logger.info("machine_entrance_open")


__all__ = ["report_machine_entrance", "report_sso_configuration"]
