"""Inputs and outputs of identity federation use cases (Presentation maps these to Pydantic)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)


@dataclass(frozen=True)
class SsoProviderDto:
    """Input for whether the login screen shows the "Sign in with SSO" button."""

    enabled: bool
    display_name: str
    #: Whether sign-out is carried through to the IdP (ADR: RP-Initiated Logout). Only when true
    #: does the screen navigate to ``/api/auth/sso/logout`` after sign-out.
    rp_logout_enabled: bool = False


@dataclass(frozen=True)
class SsoAuthorizationDto:
    """Inputs for sending to the IdP.

    ``transaction`` is the round-trip state signed and entrusted to the sending browser's cookie,
    used on return to check "is it the same browser" (stops login CSRF).
    No copy remains server-side (ADR-0077 §1).
    """

    authorization_url: str
    transaction: LoginTransaction


@dataclass(frozen=True)
class ContinuedSessionDto:
    """A login continued silently (ADR-0104). Carried over on return if it's the same person."""

    user_id: int
    active_role: str | None
    authenticated_at: datetime
    signed_in_with_passkey: bool = False


@dataclass(frozen=True)
class ResolvedAccountDto:
    """Result of resolving the IdP's identity to a user of this app.

    ``provisioned`` / ``linked`` distinguish for the audit log (newly created, or
    bound to an existing account).
    """

    user_id: int
    provisioned: bool = False
    linked: bool = False


@dataclass(frozen=True)
class SsoHandoffDto:
    """What the callback hands to the SPA (redemption ticket and return target)."""

    ticket: str
    redirect_to: str
    account: ResolvedAccountDto


@dataclass(frozen=True)
class SsoSessionDto:
    """Login result taken out of a redemption ticket.

    ``login`` is stamped into the issued tokens (ADR-0077 §3). Without it, when a logout notice
    arrives **we can't tell which tokens to invalidate**.
    """

    user_id: int
    redirect_to: str
    login: FederatedLogin


@dataclass(frozen=True)
class FederatedLinkDto:
    """The caller's own link status shown on the settings screen (ADR-0077 §5).

    If ``available`` is false, the screen hides this whole section (SSO disabled).
    """

    available: bool
    display_name: str = ""
    linked: bool = False
    linked_at: datetime | None = None


__all__ = [
    "FederatedLinkDto",
    "ResolvedAccountDto",
    "SsoAuthorizationDto",
    "SsoHandoffDto",
    "SsoProviderDto",
    "SsoSessionDto",
]
