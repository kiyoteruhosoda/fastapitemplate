"""Domain exceptions of the identity federation context.

``code`` is used as is as the API error code (display wording is the frontend's job).
Failures in the middle of a browser round trip return to the login screen as
``?sso_error=<code>`` (ADR-0077 §1).
"""

from __future__ import annotations


class IdentityFederationError(Exception):
    """Base exception of this context."""

    code = "sso_error"


class SsoNotConfiguredError(IdentityFederationError):
    """SSO is disabled, or the connection (issuer / client) is not filled in."""

    code = "sso_not_configured"


class SsoLoginTransactionInvalidError(IdentityFederationError):
    """The round-trip state can't be restored (no cookie, expired, ``state`` mismatch).

    **Browsers that drop cookies always stop here.** It's a first-party cookie, so it's separate
    from third-party cookie restrictions, but with all cookies refused even legitimate logins
    fail (ADR-0077 §1).
    """

    code = "sso_state_invalid"


class SsoTicketNotFoundError(IdentityFederationError):
    """Redemption ticket not found (expired or already used)."""

    code = "sso_ticket_invalid"


class IdentityProviderUnavailableError(IdentityFederationError):
    """Can't talk to the IdP (communication / response failure in discovery or token exchange)."""

    code = "sso_provider_unavailable"


class InvalidIdTokenError(IdentityFederationError):
    """ID token verification failed (signature, issuer, audience, nonce)."""

    code = "sso_invalid_id_token"


class InvalidLogoutTokenError(IdentityFederationError):
    """``logout_token`` verification failed (signature, issuer, audience, expiry, shape).

    **The reason is not exposed.** This endpoint can be hit unauthenticated, so detailed answers
    would give brute force a clue about "how far it got".
    """

    code = "sso_invalid_logout_token"


class SsoAcrNotSatisfiedError(IdentityFederationError):
    """The requested authentication strength (``acr_values``) is not met (ADR-0076 §3 decision 1).

    This also applies when no ``acr`` comes back. It was requested but not assured, so it must
    not pass.
    """

    code = "sso_acr_not_satisfied"


class SsoEmailMissingError(IdentityFederationError):
    """No email claim (the account can't be bound)."""

    code = "sso_email_missing"


class SsoEmailNotAllowedError(IdentityFederationError):
    """Email domain not allowed."""

    code = "sso_email_not_allowed"


class SsoAccountNotLinkedError(IdentityFederationError):
    """No matching account, and automatic creation is not allowed."""

    code = "sso_account_not_linked"


class SsoIdentityTakenError(IdentityFederationError):
    """That IdP account is bound to **a different user** (ADR-0077 §5).

    ⚠ **Refused because it would be a takeover.** Allowing rebinding would let someone sharing one
    account on the IdP side later steal the way in of another person in this app.
    """

    code = "sso_identity_taken"


class SsoAlreadyLinkedError(IdentityFederationError):
    """This user **already has** a binding to that IdP (ADR-0077 §5).

    To switch to a different ``subject``, unlink first and then link again. Silently overwriting
    would make the path that signed in via the previous binding vanish without notice.
    """

    code = "sso_already_linked"


class SsoIdentityNotLinkedError(IdentityFederationError):
    """Tried to unlink, but there is no binding to that IdP."""

    code = "sso_identity_not_linked"


class SsoLastEntranceError(IdentityFederationError):
    """Unlinking would leave this user **with no way in at all** (ADR-0077 §5).

    ⚠ **Don't create lockouts.** Removing the IdP from a user with neither a local password nor
    a passkey leaves only recovery by an administrator.
    """

    code = "sso_last_entrance"


class SsoLinkSessionMismatchError(IdentityFederationError):
    """The user who started the linking round trip differs from the session on return.

    Happens when the user signed out mid-round-trip or signed in again as someone else.
    **We can't decide which account to bind to**, so they are asked to retry.
    """

    code = "sso_link_session_mismatch"


class SsoAccountInactiveError(IdentityFederationError):
    """The account is disabled."""

    code = "sso_account_inactive"


class AppAccessTokenRejectedError(IdentityFederationError):
    """Don't accept an assay access token coming from an app (ADR-0081 §1).

    The reason (signature, audience, client, suspension) is not distinguished in the response. It becomes 401.
    """

    code = "invalid_token"


class DpopProofRejectedError(AppAccessTokenRejectedError):
    """A token with ``cnf.jkt`` lacks a matching DPoP proof (ADR-0103).

    401 with ``WWW-Authenticate: DPoP error="invalid_dpop_proof"``. The app fixes its clock and retries once.
    """

    code = "invalid_dpop_proof"


class MachineNotBoundToApplicationError(IdentityFederationError):
    """The claimed service account isn't bound to any app in assay (403 from the admin API. ADR-0077 §7).

    ⚠ **Not a fault but "not set up yet".** assay decides whose roster to return from the
    caller's service account, so it keeps returning this until bound.
    """

    code = "machine_not_bound_to_application"


class MachineEntranceClosedError(IdentityFederationError):
    """The machine endpoint is not open (audience ``MACHINE_AUDIENCE`` or allowlist ``MACHINE_CLIENTS``
    is empty. ADR-0082 §2 decision 4)."""

    code = "machine_entrance_closed"


class InvalidMachineTokenError(IdentityFederationError):
    """Can't accept as a machine token (signature, issuer, expiry, audience or subject)."""

    code = "machine_token_invalid"


class MachineClientNotRegisteredError(IdentityFederationError):
    """The claimed ``client_id`` is not in the allowlist."""

    code = "machine_client_not_registered"

    def __init__(self, client_id: str) -> None:
        super().__init__(self.code)
        #: The claimed machine (kept as the audit target. A public identifier)
        self.client_id = client_id


class MachineActorNotFoundError(IdentityFederationError):
    """No active user matching the allowlist's ``acts_as`` exists in the token issuer's tenant."""

    code = "machine_actor_not_found"

    def __init__(self, client_id: str) -> None:
        super().__init__(self.code)
        #: The claimed machine (kept as the audit target. A public identifier)
        self.client_id = client_id


__all__ = [
    "DpopProofRejectedError",
    "IdentityFederationError",
    "IdentityProviderUnavailableError",
    "InvalidIdTokenError",
    "InvalidLogoutTokenError",
    "InvalidMachineTokenError",
    "MachineActorNotFoundError",
    "MachineClientNotRegisteredError",
    "MachineEntranceClosedError",
    "MachineNotBoundToApplicationError",
    "SsoAccountInactiveError",
    "SsoAccountNotLinkedError",
    "SsoAcrNotSatisfiedError",
    "SsoAlreadyLinkedError",
    "SsoEmailMissingError",
    "SsoEmailNotAllowedError",
    "SsoIdentityNotLinkedError",
    "SsoIdentityTakenError",
    "SsoLastEntranceError",
    "SsoLinkSessionMismatchError",
    "SsoLoginTransactionInvalidError",
    "SsoNotConfiguredError",
    "SsoTicketNotFoundError",
]
