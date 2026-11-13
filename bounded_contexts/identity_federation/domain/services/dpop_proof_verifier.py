"""Endpoint verifying the shape and signature of DPoP proofs (ADR-0103. Implemented in Infrastructure)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.value_objects.dpop_proof import (
    DpopProofRequirements,
    VerifiedDpopProof,
)


class DpopProofVerifier(Protocol):
    def verify(self, proof: str, requirements: DpopProofRequirements) -> VerifiedDpopProof:
        """Check ``typ``, ``alg`` (ES256), ``jwk`` (P-256 public key), signature, ``htm``, ``htu``, ``iat`` and ``ath``.

        On mismatch ``DpopProofRejectedError``. Reuse (``jti``) is not checked (recording is the caller's job).
        """
        ...


__all__ = ["DpopProofVerifier"]
