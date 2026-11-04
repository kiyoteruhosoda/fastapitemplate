"""DPoP の証明の形と署名を確かめる口（ADR-0103。実装は Infrastructure 層）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.value_objects.dpop_proof import (
    DpopProofRequirements,
    VerifiedDpopProof,
)


class DpopProofVerifier(Protocol):
    def verify(self, proof: str, requirements: DpopProofRequirements) -> VerifiedDpopProof:
        """``typ``・``alg``（ES256）・``jwk``（P-256 の公開鍵）・署名・``htm``・``htu``・``iat``・``ath`` を見る。

        合わなければ ``DpopProofRejectedError``。使い回し（``jti``）は見ない（記録は呼び出し側）。
        """
        ...


__all__ = ["DpopProofVerifier"]
