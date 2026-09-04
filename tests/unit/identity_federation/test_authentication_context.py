"""要求した認証の強度の確かめ方（ADR-0026 決定 1）。"""

from __future__ import annotations

import pytest

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAcrNotSatisfiedError,
)
from bounded_contexts.identity_federation.domain.value_objects.authentication_context import (
    RequestedAuthenticationContext,
)


def test_nothing_is_required_by_default() -> None:
    """既定は要求しない。連携先が予約語を持たない派生でも従来どおり動く。"""
    context = RequestedAuthenticationContext()
    assert not context.is_requested
    context.ensure_satisfied(None)


def test_a_matching_acr_passes() -> None:
    context = RequestedAuthenticationContext(values=("urn:assay:ac:mfa",))
    context.ensure_satisfied("urn:assay:ac:mfa")


def test_a_weaker_acr_is_refused() -> None:
    context = RequestedAuthenticationContext(values=("urn:assay:ac:mfa",))
    with pytest.raises(SsoAcrNotSatisfiedError):
        context.ensure_satisfied("urn:assay:ac:single")


def test_a_missing_acr_is_refused() -> None:
    """⚠ ここが肝。返ってこないものを「満たした」と読むと、要求は送っただけになる。"""
    context = RequestedAuthenticationContext(values=("urn:assay:ac:mfa",))
    with pytest.raises(SsoAcrNotSatisfiedError):
        context.ensure_satisfied(None)
