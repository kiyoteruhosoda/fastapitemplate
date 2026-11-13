"""Subject of a machine token (ADR-0082 §1 decision 3).

Signature, issuer, expiry and audience are checked by the gateway. This checks **that the subject is the
client itself**:

- ``sub_type == "client"`` — the only marker distinguishing it from a user's login token
- ``sub == client_id`` — assay builds the two from separate inputs, so check they agree

⚠ Kept in this one place rather than in each implementation (forgetting it would let someone's login token
through the machine endpoint).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bounded_contexts.identity_federation.domain.exceptions import InvalidMachineTokenError

CLIENT_SUBJECT_TYPE = "client"


@dataclass(frozen=True)
class MachineClaims:
    client_id: str

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> MachineClaims:
        if claims.get("sub_type") != CLIENT_SUBJECT_TYPE:
            raise InvalidMachineTokenError
        subject = claims.get("sub")
        client_id = claims.get("client_id")
        if not isinstance(subject, str) or not subject or subject != client_id:
            raise InvalidMachineTokenError
        return cls(client_id=subject)


__all__ = ["CLIENT_SUBJECT_TYPE", "MachineClaims"]
