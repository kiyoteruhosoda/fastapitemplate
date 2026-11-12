"""Resolve an assay access token coming from an app to a user of this app (ADR-0081 §1).

Acceptance conditions (failing any one gives the same 401):

- Signature, ``typ``, issuer, audience, expiry (checked by the gateway)
- ``client_id`` belongs to an app we may accept
- No ``sub_type`` (not a machine token)
- Not hit by a logout record (ADR-0077 §3)
- If ``cnf.jkt`` is present, it comes with ``Authorization: DPoP`` and a proof made with that key
  (ADR-0103).
    Each proof is single-use per key. Without ``cnf``, ``Bearer`` only (existing apps)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bounded_contexts.identity_federation.application.use_cases.resolve_federated_account import (
    ResolveFederatedAccount,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    AppAccessTokenRejectedError,
    DpopProofRejectedError,
)
from bounded_contexts.identity_federation.domain.repositories.dpop_proof_replay_repository import (
    DpopProofReplayRepository,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.services.app_token_gateway import AppTokenGateway
from bounded_contexts.identity_federation.domain.services.dpop_proof_verifier import DpopProofVerifier
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import ClaimsMapping
from bounded_contexts.identity_federation.domain.value_objects.dpop_proof import DpopProofRequirements
from bounded_contexts.identity_federation.domain.value_objects.federated_login import FederatedLogin
from bounded_contexts.identity_federation.domain.value_objects.federated_session import FederatedSession
from bounded_contexts.identity_federation.domain.value_objects.presented_app_token import PresentedAppToken
from shared.kernel.timestamps import utcnow_aware


@dataclass(frozen=True)
class AppTokenAcceptance:
    """Whose tokens to accept (built from settings)."""

    issuer: str
    client_ids: frozenset[str]


@dataclass(frozen=True)
class AuthenticateAppAccessToken:
    acceptance: AppTokenAcceptance
    gateway: AppTokenGateway
    identities: FederatedIdentityRepository
    revocations: SessionRevocationRepository
    claims: ClaimsMapping
    accounts: ResolveFederatedAccount
    dpop_proofs: DpopProofVerifier
    dpop_replays: DpopProofReplayRepository

    def execute(self, presented: PresentedAppToken) -> int:
        """Return the user's id if acceptable."""
        if not (self.acceptance.issuer and self.acceptance.client_ids):
            raise AppAccessTokenRejectedError
        claims = self.gateway.verify_access_token(self.acceptance.issuer, presented.token)
        bound_key = _bound_key(claims)
        self._check_possession(presented, bound_key)
        subject = self._accepted_subject(claims)
        identity = self.identities.find(self.acceptance.issuer, subject)
        if identity is not None:
            return identity.user_id
        return self._first_visit(presented, subject, bound=bound_key is not None)

    def _check_possession(self, presented: PresentedAppToken, bound_key: str | None) -> None:
        """Whether the presentation scheme matches the token's binding (ADR-0103).

        ⚠ **Don't accept a bound token via ``Bearer``.** Doing so would let anyone who copied just the token use it.
        """
        if bound_key is None:
            if presented.dpop:
                raise AppAccessTokenRejectedError
            return
        if not presented.dpop:
            raise AppAccessTokenRejectedError
        if presented.proof is None:
            raise DpopProofRejectedError
        verified = self.dpop_proofs.verify(
            presented.proof,
            DpopProofRequirements(
                method=presented.method,
                uri=presented.uri,
                access_token=presented.token,
                now=utcnow_aware(),
            ),
        )
        if verified.jkt != bound_key:
            raise DpopProofRejectedError
        if not self.dpop_replays.record_if_unused(verified.replay_key, verified.retain_until):
            raise DpopProofRejectedError

    def _accepted_subject(self, claims: Mapping[str, Any]) -> str:
        subject = str(claims.get("sub") or "")
        if not subject or "sub_type" in claims:
            raise AppAccessTokenRejectedError
        if str(claims.get("client_id") or "") not in self.acceptance.client_ids:
            raise AppAccessTokenRejectedError
        # Treat ``iat`` as the session start. It renews on every refresh, but assay refuses refreshes
        # for suspended users, so no ``iat`` later than the suspension appears.
        started_at = datetime.fromtimestamp(int(claims["iat"]), tz=UTC).replace(tzinfo=None)
        login = FederatedLogin(FederatedSession(self.acceptance.issuer, subject), started_at)
        if self.revocations.is_revoked(login):
            raise AppAccessTokenRejectedError
        return subject

    def _first_visit(self, presented: PresentedAppToken, subject: str, *, bound: bool) -> int:
        """A person arriving from an app first. Created / merged by the same rules as SSO login
        (ADR-0081 §1 decision 4).

        With a bound token, assay's userinfo can't be fetched (this server doesn't hold the key), so
        the ID token sent by the app is read after verifying its signature (ADR-0103).
        """
        profile = dict(self._profile(presented, bound=bound))
        if profile.get("sub") not in (None, subject):
            profile = {}
        profile["sub"] = subject
        resolved = self.accounts.execute(issuer=self.acceptance.issuer, user=self.claims.apply(profile))
        return resolved.user_id

    def _profile(self, presented: PresentedAppToken, *, bound: bool) -> Mapping[str, Any]:
        if not bound:
            return self.gateway.userinfo(self.acceptance.issuer, presented.token)
        if presented.id_token is None:
            return {}
        return self.gateway.verify_id_token(self.acceptance.issuer, presented.id_token, self.acceptance.client_ids)


def _bound_key(claims: Mapping[str, Any]) -> str | None:
    """``cnf.jkt`` (thumbprint of the key bound via DPoP). ``None`` if absent."""
    confirmation = claims.get("cnf")
    if confirmation is None:
        return None
    jkt = confirmation.get("jkt") if isinstance(confirmation, Mapping) else None
    if not isinstance(jkt, str) or not jkt:
        # An unreadable binding isn't treated as "absent" (that would let it pass as Bearer)
        raise AppAccessTokenRejectedError
    return jkt


__all__ = ["AppTokenAcceptance", "AuthenticateAppAccessToken"]
