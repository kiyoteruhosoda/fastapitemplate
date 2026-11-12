"""A token from an app and how it was presented (ADR-0081 §1, ADR-0103)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresentedAppToken:
    """Bundle of the ``Authorization`` scheme, the ``DPoP`` proof and the request target.

    Tokens with ``cnf.jkt`` need the ``DPoP`` scheme and a proof; tokens without it use ``Bearer`` only.
    """

    token: str
    #: Whether it came as ``Authorization: DPoP`` (``False`` means ``Bearer``).
    dpop: bool
    #: Proof from the ``DPoP`` header.
    proof: str | None
    #: Uppercase HTTP method.
    method: str
    #: This endpoint's URL as this server presents it externally (no query).
    uri: str
    #: ID token the app received in the same login. Used for the profile when first arriving with a bound token.
    id_token: str | None = None


__all__ = ["PresentedAppToken"]
