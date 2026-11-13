"""What is required of a DPoP (RFC 9449) proof, and a verified proof (ADR-0103).

Accepts the same window as assay (assay ADR-0075 decision 6): ``iat`` from 120 s before now to 60 s after.
Each ``jti`` is single-use per key and remembered until the accepted window closes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

#: How far before now ``iat`` is accepted.
MAX_PROOF_AGE = timedelta(seconds=120)
#: How far after now ``iat`` is accepted (for device clocks running ahead).
MAX_CLOCK_AHEAD = timedelta(seconds=60)


@dataclass(frozen=True)
class DpopProofRequirements:
    """What a proof must satisfy.

    ``uri`` is **the URL this server presents externally** (``APP_BASE_URL`` + path). Built from
    ``Host`` behind the front proxy, it would differ from the URL the app signed.
    """

    method: str
    uri: str
    access_token: str
    #: tz-aware UTC.
    now: datetime


@dataclass(frozen=True)
class VerifiedDpopProof:
    #: Key thumbprint (RFC 7638 JWK Thumbprint). Compared with the token's ``cnf.jkt``.
    jkt: str
    jti: str
    #: tz-aware UTC.
    issued_at: datetime

    @property
    def replay_key(self) -> str:
        """Key of the reuse-detection record. ``jti`` uniqueness is per key."""
        return hashlib.sha256(f"{self.jkt}:{self.jti}".encode()).hexdigest()

    @property
    def retain_until(self) -> datetime:
        """Past this time the same proof is refused by time (keeping the record until then is enough)."""
        return self.issued_at + MAX_PROOF_AGE


__all__ = ["MAX_CLOCK_AHEAD", "MAX_PROOF_AGE", "DpopProofRequirements", "VerifiedDpopProof"]
