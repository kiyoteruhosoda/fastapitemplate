"""受け入れてよい相手か・寄せてよいか（ADR-0025 決定 4 / ADR-0037）。"""

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


def test_by_default_nothing_is_linked() -> None:
    """⚠ 既定は寄せない（ADR-0037）。

    条件の ``email_verified`` は、自前 idp (assay) では「テナント管理者がそう
    主張している」であって本人の証明ではない。既定で開けておくと、意味の食い違いが
    そのまま乗っ取りの経路になる。
    """
    assert not AccountLinkingPolicy().may_link(_user())


def test_an_unverified_address_is_never_linked() -> None:
    """開けていても、検証していないアドレスでは寄せない。"""
    assert not AccountLinkingPolicy(link_by_email=True).may_link(_user(verified=False))


def test_linking_happens_only_when_it_is_turned_on() -> None:
    assert AccountLinkingPolicy(link_by_email=True).may_link(_user())
