"""Settings for one external IdP (OpenID Provider) connection.

This app has only one IdP, and values are built from settings (``OIDC_*`` in ``settings``)
(ADR-0077 §1). This receives the built values and only judges "are the settings usable" and
"which scope goes into the authorization request".
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.value_objects.client_credential import (
    ClientCredential,
)

# OpenID Connect returns no ID token without the ``openid`` scope. Always request it,
# even if it is missing from the settings.
REQUIRED_SCOPE = "openid"


@dataclass(frozen=True)
class IdentityProvider:
    display_name: str
    issuer: str
    client_id: str
    credential: ClientCredential
    redirect_uri: str
    scopes: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """Whether an authorization request can be started (connection and credentials complete).

        Whether credentials are complete differs per method, so it is left to
        :class:`ClientCredential` (ADR-0077 §1).
        """
        return bool(self.issuer and self.client_id and self.redirect_uri and self.credential.is_complete)

    @property
    def scope_parameter(self) -> str:
        """Value of the ``scope`` parameter. ``openid`` always first, duplicates collapsed."""
        requested = (REQUIRED_SCOPE, *(scope for scope in self.scopes if scope))
        return " ".join(dict.fromkeys(requested))


def require_usable(provider: IdentityProvider | None) -> IdentityProvider:
    """Check the settings are usable and return them. Otherwise :class:`SsoNotConfiguredError`.

    The caller needn't distinguish "disabled" from "settings not filled in"
    (both lead to the single result that SSO can't start).
    """
    if provider is None or not provider.is_usable:
        raise SsoNotConfiguredError
    return provider


__all__ = ["REQUIRED_SCOPE", "IdentityProvider", "require_usable"]
