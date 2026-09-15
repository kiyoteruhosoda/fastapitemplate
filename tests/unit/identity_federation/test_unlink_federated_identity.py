"""連携の解除 ——外したあと入れなくなる利用者を作らない（ADR-0040）。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from bounded_contexts.identity_federation.application.use_cases.unlink_federated_identity import (
    UnlinkFederatedIdentity,
)
from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    SsoIdentityNotLinkedError,
    SsoLastEntranceError,
)

_ISSUER = "https://idp.example.test"
_ME = 7


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


def _linked() -> _Identities:
    return _Identities([FederatedIdentity(_ISSUER, "idp-subject", _ME)])


def test_a_link_with_another_entrance_left_can_be_removed() -> None:
    identities = _linked()
    UnlinkFederatedIdentity(identities).execute(issuer=_ISSUER, user_id=_ME, has_other_entrance=True)
    assert identities.rows == []


def test_the_last_entrance_is_not_removed() -> None:
    """⚠ 締め出しを作らない。残るのは管理者による復旧だけになる。"""
    identities = _linked()
    with pytest.raises(SsoLastEntranceError):
        UnlinkFederatedIdentity(identities).execute(issuer=_ISSUER, user_id=_ME, has_other_entrance=False)
    assert len(identities.rows) == 1


def test_removing_a_link_that_is_not_there_says_so() -> None:
    with pytest.raises(SsoIdentityNotLinkedError):
        UnlinkFederatedIdentity(_Identities()).execute(issuer=_ISSUER, user_id=_ME, has_other_entrance=True)
