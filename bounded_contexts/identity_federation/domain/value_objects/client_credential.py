"""Credentials presented to the token endpoint (ADR-0077 §1).

There are two methods. Both prove "this is the client itself" and are used
**only when redeeming the authorization code**.

``client_secret_basic``
    Sends a shared secret via Basic authentication. The settings hold the secret itself.
``private_key_jwt``
    Sends an assertion signed with a private key on the host (RFC 7523). The settings carry only
    **the key's location**; the secret itself never appears in app settings or deploy
    variables.
"""

from __future__ import annotations

from dataclasses import dataclass

CLIENT_SECRET_BASIC = "client_secret_basic"
PRIVATE_KEY_JWT = "private_key_jwt"

#: Methods accepted as settings. Values not listed here are treated as "misconfigured" (ADR-0077 §1).
CLIENT_AUTH_METHODS = (CLIENT_SECRET_BASIC, PRIVATE_KEY_JWT)


@dataclass(frozen=True)
class ClientCredential:
    """A method and the inputs it needs.

    Inputs differ per method, so **whether they are complete also differs per method**.
    Values not held here (empty string) mean "not configured".
    """

    method: str
    secret: str = ""
    private_key_file: str = ""
    private_key_kid: str = ""

    @property
    def is_complete(self) -> bool:
        """Whether the inputs are complete enough to authenticate with that method.

        ⚠ **Don't fall back to the default method on a misspelling.** Silently treating a value like
        ``private-key-jwt`` as ``client_secret_basic`` would only get an unexplained ``invalid_client``
        from the IdP. Unknown methods are misconfiguration.
        """
        if self.method == PRIVATE_KEY_JWT:
            return bool(self.private_key_file)
        if self.method == CLIENT_SECRET_BASIC:
            return bool(self.secret)
        return False

    @property
    def uses_private_key(self) -> bool:
        return self.method == PRIVATE_KEY_JWT


__all__ = [
    "CLIENT_AUTH_METHODS",
    "CLIENT_SECRET_BASIC",
    "PRIVATE_KEY_JWT",
    "ClientCredential",
]
