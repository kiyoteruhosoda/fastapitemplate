"""Pydantic schemas for SSO login."""

from __future__ import annotations

from pydantic import BaseModel, Field

from presentation.fastapi.schemas.types import UtcDatetime


class SsoProviderResponse(BaseModel):
    """Input for whether the login screen shows the "Sign in with SSO" button.

    Readable unauthenticated, so it carries no connection URL or client ID.
    """

    enabled: bool
    display_name: str
    #: Whether the password / passkey entrances are open (ADR-0076 §3 decision 2). If false,
    #: the login screen hides the password fields and the passkey button.
    local_login_enabled: bool = True
    #: Whether sign-out is carried through to the IdP. Only when true does the screen navigate
    #: to ``/api/auth/sso/logout`` after finishing the app sign-out.
    rp_logout_enabled: bool = False


class SsoTicketRequest(BaseModel):
    """Redemption ticket handed over by the callback."""

    ticket: str = Field(min_length=1, max_length=255)


class SsoSessionResponse(BaseModel):
    """Redemption result. ``redirect_to`` is the screen where SSO started (an SPA route).

    ⚠ **No tokens in it** (ADR-0076 §4). They are carried in cookies.
    """

    expires_in: int
    redirect_to: str


class FederatedLinkResponse(BaseModel):
    """The caller's own link status shown on the settings screen (ADR-0077 §5).

    ⚠ **The peer's ``subject`` is not included.** There's no point showing it, and including it
    would leak the IdP's internal identifier into browser history and logs.
    """

    #: Whether SSO itself is usable. If false, the screen hides this section.
    available: bool
    display_name: str = ""
    linked: bool = False
    linked_at: UtcDatetime | None = None
    #: Whether a way in remains after removing the link (ADR-0077 §5). If false, the screen hides
    #: the unlink button.
    can_unlink: bool = False


class SsoLinkStartResponse(BaseModel):
    """Entrance to the linking round trip. The screen navigates to this URL **itself**.

    The round-trip state cookie is set by this response. The server doesn't return 303 because
    this is XHR — if authentication has expired it can return 401 and the screen can offer a retry.
    """

    authorization_url: str


__all__ = [
    "FederatedLinkResponse",
    "SsoLinkStartResponse",
    "SsoProviderResponse",
    "SsoSessionResponse",
    "SsoTicketRequest",
]
