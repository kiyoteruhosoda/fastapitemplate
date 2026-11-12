"""How the requested authentication strength is verified (ADR-0076 §3 decision 1)."""

from __future__ import annotations

import pytest

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoAcrNotSatisfiedError,
)
from bounded_contexts.identity_federation.domain.value_objects.authentication_context import (
    RequestedAuthenticationContext,
)


def test_nothing_is_required_by_default() -> None:
    """Not requested by default. Derived apps whose partner has no reserved values keep working as before."""
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
    """⚠ This is the crux. Reading something not returned as "satisfied" would make the request merely sent."""
    context = RequestedAuthenticationContext(values=("urn:assay:ac:mfa",))
    with pytest.raises(SsoAcrNotSatisfiedError):
        context.ensure_satisfied(None)
