"""連携の完了 ——誰の口座へ結び付くかの判断（ADR-0040）。

IdP との往復そのものは :mod:`tests.integration.api.test_sso_login` が見る。ここで
確かめるのは**結び付けてよい相手かどうか**だけ。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from bounded_contexts.identity_federation.application.use_cases.complete_sso_link import (
    CompleteSsoLink,
)
from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAlreadyLinkedError,
    SsoIdentityTakenError,
    SsoLinkSessionMismatchError,
    SsoLoginTransactionInvalidError,
)
from bounded_contexts.identity_federation.domain.services.oidc_provider_gateway import (
    AuthorizationRequest,
    CodeExchange,
    EndSessionRequest,
    LogoutTokenVerification,
)
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import (
    ClaimsMapping,
)
from bounded_contexts.identity_federation.domain.value_objects.client_credential import (
    ClientCredential,
)
from bounded_contexts.identity_federation.domain.value_objects.identity_provider import (
    IdentityProvider,
)
from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)
from bounded_contexts.identity_federation.domain.value_objects.sso_callback import (
    SsoCallback,
)
from bounded_contexts.identity_federation.domain.value_objects.transaction_purpose import (
    TransactionPurpose,
)

_ISSUER = "https://idp.example.test"
_ME = 7
_SOMEONE_ELSE = 8


@dataclass
class _Gateway:
    subject: str = "idp-subject"

    def authorization_url(self, request: AuthorizationRequest) -> str:
        return f"{_ISSUER}/authorize?state={request.state}"

    def exchange_code(self, exchange: CodeExchange) -> Mapping[str, Any]:
        return {"sub": self.subject, "email": "someone@example.com", "email_verified": True}

    def end_session_url(self, request: EndSessionRequest) -> str | None:
        return None

    def verify_logout_token(self, verification: LogoutTokenVerification) -> Mapping[str, Any]:
        raise NotImplementedError


@dataclass
class _Identities:
    rows: list[FederatedIdentity] = field(default_factory=list)

    def find(self, issuer: str, subject: str) -> FederatedIdentity | None:
        return next((r for r in self.rows if r.issuer == issuer and r.subject == subject), None)

    def find_for_user(self, issuer: str, user_id: int) -> FederatedIdentity | None:
        return next((r for r in self.rows if r.issuer == issuer and r.user_id == user_id), None)

    def link(self, identity: FederatedIdentity) -> FederatedIdentity:
        self.rows.append(identity)
        return identity

    def unlink(self, identity: FederatedIdentity) -> None:
        self.rows.remove(identity)

    def touch(self, identity: FederatedIdentity) -> None:
        return None


def _provider() -> IdentityProvider:
    return IdentityProvider(
        display_name="IdP",
        issuer=_ISSUER,
        client_id="rp",
        credential=ClientCredential(method="client_secret_basic", secret="shhh"),
        redirect_uri="https://app.example.test/api/auth/sso/callback",
    )


def _use_case(identities: _Identities) -> CompleteSsoLink:
    return CompleteSsoLink(
        provider=_provider(),
        gateway=_Gateway(),
        identities=identities,
        claims=ClaimsMapping(),
    )


def _callback(*, user_id: int | None = _ME, state: str = "s") -> SsoCallback:
    transaction = LoginTransaction(
        state="s",
        nonce="n",
        code_verifier="v",
        purpose=TransactionPurpose.LINK,
        user_id=user_id,
    )
    return SsoCallback(code="c", state=state, transaction=transaction)


def test_the_identity_is_linked_to_whoever_started_the_round_trip() -> None:
    identities = _Identities()
    _use_case(identities).execute(callback=_callback(), user_id=_ME)
    assert identities.rows == [FederatedIdentity(issuer=_ISSUER, subject="idp-subject", user_id=_ME)]


def test_a_round_trip_without_state_is_refused() -> None:
    with pytest.raises(SsoLoginTransactionInvalidError):
        _use_case(_Identities()).execute(callback=_callback(state="other"), user_id=_ME)


def test_a_round_trip_started_by_someone_else_is_refused() -> None:
    """⚠ 往復の途中で入れ替わったブラウザで、別人の口座へ結び付けない。"""
    with pytest.raises(SsoLinkSessionMismatchError):
        _use_case(_Identities()).execute(callback=_callback(user_id=_SOMEONE_ELSE), user_id=_ME)


def test_a_round_trip_without_an_owner_is_refused() -> None:
    """ログインの往復（``user_id`` が無い）を連携として完了させない。"""
    with pytest.raises(SsoLinkSessionMismatchError):
        _use_case(_Identities()).execute(callback=_callback(user_id=None), user_id=_ME)


def test_an_identity_that_belongs_to_another_user_is_refused() -> None:
    """⚠ 横取りになる。IdP 側で口座を共有している相手に入り口を奪わせない。"""
    identities = _Identities([FederatedIdentity(_ISSUER, "idp-subject", _SOMEONE_ELSE)])
    with pytest.raises(SsoIdentityTakenError):
        _use_case(identities).execute(callback=_callback(), user_id=_ME)


def test_linking_the_same_identity_again_is_not_an_error() -> None:
    """同じ相手をもう一度押しても断らない（利用者から見れば結果は同じ）。"""
    identities = _Identities([FederatedIdentity(_ISSUER, "idp-subject", _ME)])
    _use_case(identities).execute(callback=_callback(), user_id=_ME)
    assert all(row.user_id == _ME for row in identities.rows)


def test_a_second_account_at_the_same_provider_is_refused() -> None:
    """既にある結び付きを黙って差し替えない（前の入り口が予告なく消える）。"""
    identities = _Identities([FederatedIdentity(_ISSUER, "another-subject", _ME)])
    with pytest.raises(SsoAlreadyLinkedError):
        _use_case(identities).execute(callback=_callback(), user_id=_ME)
