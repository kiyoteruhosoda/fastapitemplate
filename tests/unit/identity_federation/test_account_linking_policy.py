"""受け入れてよい相手か・寄せてよいか（ADR-0025 決定 4）。"""

from __future__ import annotations

import pytest

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoEmailNotAllowedError,
)
from bounded_contexts.identity_federation.domain.value_objects.account_linking_policy import (
    AccountLinkingPolicy,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_user import (
    FederatedUser,
)


def _user(*, email: str = "someone@example.com", verified: bool = True) -> FederatedUser:
    return FederatedUser(subject="sub", email=email, username="someone", email_verified=verified)


def test_no_domain_restriction_accepts_anyone() -> None:
    AccountLinkingPolicy().ensure_accepted(_user())


def test_a_domain_outside_the_list_is_refused() -> None:
    policy = AccountLinkingPolicy(allowed_email_domains=("example.com",))
    with pytest.raises(SsoEmailNotAllowedError):
        policy.ensure_accepted(_user(email="someone@evil.test"))


def test_an_unverified_address_is_never_linked() -> None:
    """検証していないアドレスで寄せると、名乗るだけで他人のアカウントへ入れる。"""
    assert not AccountLinkingPolicy().may_link(_user(verified=False))


def test_linking_can_be_turned_off_entirely() -> None:
    assert not AccountLinkingPolicy(link_by_email=False).may_link(_user())
