"""アプリから来た assay のアクセストークンを、このアプリの利用者へ落とす（ADR-0081 §1）。

受け取る条件（どれか 1 つでも外れたら同じ 401）:

- 署名・``typ``・発行者・宛先・期限（ゲートウェイが確かめる）
- ``client_id`` が受け取ってよいアプリのもの
- ``sub_type`` が無い（機械のトークンではない）
- 停止の記録（ADR-0077 §3）に当たらない
- ``cnf.jkt`` があれば、``Authorization: DPoP`` と、その鍵で作った証明が付いている（ADR-0103）。
  証明は鍵ごとに 1 回だけ。``cnf`` が無ければ ``Bearer`` だけ（今までのアプリ）
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
    """誰のトークンを受け取るか（設定から起こす）。"""

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
        """受け取れるなら利用者の id を返す。"""
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
        """出し方とトークンの結び付けが合うか（ADR-0103）。

        ⚠ **結び付けたトークンを ``Bearer`` で受けない。** 受けると、トークンだけを写した者が使える。
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
        # セッションの始まりは ``iat`` とみなす。更新のたびに新しくなるが、停止した利用者の
        # 更新は assay が断るので、停止より後の ``iat`` は現れない。
        started_at = datetime.fromtimestamp(int(claims["iat"]), tz=UTC).replace(tzinfo=None)
        login = FederatedLogin(FederatedSession(self.acceptance.issuer, subject), started_at)
        if self.revocations.is_revoked(login):
            raise AppAccessTokenRejectedError
        return subject

    def _first_visit(self, presented: PresentedAppToken, subject: str, *, bound: bool) -> int:
        """アプリから先に来た人。SSO のログインと同じ規則で作る・寄せる（ADR-0081 §1 決定 4）。

        結び付けたトークンでは assay の userinfo を引けない（このサーバーは鍵を持たない）ので、
        アプリが送った ID トークンの署名を確かめて読む（ADR-0103）。
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
    """``cnf.jkt``（DPoP で結び付けた鍵の指紋）。無ければ ``None``。"""
    confirmation = claims.get("cnf")
    if confirmation is None:
        return None
    jkt = confirmation.get("jkt") if isinstance(confirmation, Mapping) else None
    if not isinstance(jkt, str) or not jkt:
        # 読めない結び付けは「無い」に倒さない（倒すと Bearer で通ってしまう）
        raise AppAccessTokenRejectedError
    return jkt


__all__ = ["AppTokenAcceptance", "AuthenticateAppAccessToken"]
