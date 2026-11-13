"""Whether a counterpart may be accepted, and whether it may be merged (ADR-0077 §1 decision 4 / ADR-0077 §4)."""

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
    """⚠ Merging is off by default (ADR-0077 §4).

    The condition ``email_verified``, with our own idp (assay), means "the tenant administrator claims
    so", not proof by the person. Leaving it open by default would turn that difference in meaning
    directly into a takeover path.
    """
    assert not AccountLinkingPolicy().may_link(_user())


def test_an_unverified_address_is_never_linked() -> None:
    """Even when enabled, unverified addresses are not merged."""
    assert not AccountLinkingPolicy(link_by_email=True).may_link(_user(verified=False))


def test_linking_happens_only_when_it_is_turned_on() -> None:
    assert AccountLinkingPolicy(link_by_email=True).may_link(_user())
