"""Whether to require two-factor authentication for password logins (ADR-0093).

⚠ **Decided again every time a token is issued.** The refresh endpoint goes through it too, so
turning the setting on affects current logins within 5 minutes, and it is lifted on the next
refresh after enrolling.
"""

from __future__ import annotations

from sqlalchemy.orm import object_session

from bounded_contexts.account_security.infrastructure.sql_local_factor_directory import (
    SqlLocalFactorDirectory,
)
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from shared.infrastructure.models import User
from shared.kernel.settings.settings import settings


def needs_two_factor_setup(user: User, carry: SessionCarryOver) -> bool:
    """SSO relies on the IdP's strength (ADR-0076 §3) and a passkey satisfies two factors on its own;
    only passwords remain."""
    if not settings.local_two_factor_required or carry.federated_login is not None or carry.signed_in_with_passkey:
        return False
    session = object_session(user)
    if session is None:  # pragma: no cover - every caller passes a user loaded from the DB
        raise RuntimeError("the user must belong to a session")
    return not SqlLocalFactorDirectory(session).factors_of(user.id).totp


__all__ = ["needs_two_factor_setup"]
