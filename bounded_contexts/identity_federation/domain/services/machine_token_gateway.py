"""Endpoint for verifying machine tokens (assay ``client_credentials``) (ADR-0082 §1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class MachineTokenGateway(Protocol):
    def verify_machine_token(self, issuer: str, audience: str, token: str) -> Mapping[str, Any]:
        """Check signature, issuer, expiry and audience (``aud``) and return the claims.

        On mismatch ``InvalidMachineTokenError``; if the IdP is unreachable, ``IdentityProviderUnavailableError``.
        ⚠ The audience is always checked (never call with empty; the caller refuses first).
        """
        ...


__all__ = ["MachineTokenGateway"]
