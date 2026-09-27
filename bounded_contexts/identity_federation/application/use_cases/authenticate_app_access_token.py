"""アプリから来た assay のアクセストークンを、このアプリの利用者へ落とす（ADR-0045）。

受け取る条件（どれか 1 つでも外れたら同じ 401）:

- 署名・``typ``・発行者・宛先・期限（ゲートウェイが確かめる）
- ``client_id`` が受け取ってよいアプリのもの
- ``sub_type`` が無い（機械のトークンではない）
- 停止の記録（ADR-0036）に当たらない
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bounded_contexts.identity_federation.application.use_cases.resolve_federated_account import (
    ResolveFederatedAccount,
)
from bounded_contexts.identity_federation.domain.exceptions import AppAccessTokenRejectedError
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.services.app_token_gateway import AppTokenGateway
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import ClaimsMapping
from bounded_contexts.identity_federation.domain.value_objects.federated_login import FederatedLogin
from bounded_contexts.identity_federation.domain.value_objects.federated_session import FederatedSession


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

    def execute(self, token: str) -> int:
        """受け取れるなら利用者の id を返す。"""
        if not (self.acceptance.issuer and self.acceptance.client_ids):
            raise AppAccessTokenRejectedError
        claims = self.gateway.verify_access_token(self.acceptance.issuer, token)
        subject = self._accepted_subject(claims)
        identity = self.identities.find(self.acceptance.issuer, subject)
        if identity is not None:
            return identity.user_id
        return self._first_visit(token, subject)

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

    def _first_visit(self, token: str, subject: str) -> int:
        """アプリから先に来た人。SSO のログインと同じ規則で作る・寄せる（ADR-0045 決定 4）。"""
        profile = dict(self.gateway.userinfo(self.acceptance.issuer, token))
        if profile.get("sub") not in (None, subject):
            profile = {}
        profile["sub"] = subject
        resolved = self.accounts.execute(issuer=self.acceptance.issuer, user=self.claims.apply(profile))
        return resolved.user_id


__all__ = ["AppTokenAcceptance", "AuthenticateAppAccessToken"]
