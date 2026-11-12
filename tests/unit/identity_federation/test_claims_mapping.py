"""Claims -> user copy (ADR-0077 §6 / idp ADR-0049 G5, G7).

⚠ **The email address is not a key, so it works without one.** Rejecting it was a leftover from
when it was the key; it is only needed "when merging on first sign-in" and "when creating a user".
"""

from __future__ import annotations

import pytest

from bounded_contexts.identity_federation.domain.exceptions import InvalidIdTokenError
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import (
    ClaimsMapping,
)


def test_a_token_without_a_subject_is_not_a_token() -> None:
    with pytest.raises(InvalidIdTokenError):
        ClaimsMapping().apply({"email": "someone@example.com"})


def test_an_email_is_read_and_lowercased() -> None:
    user = ClaimsMapping().apply({"sub": "s", "email": "Someone@Example.COM"})
    assert user.email == "someone@example.com"


def test_a_token_without_an_email_still_names_a_user() -> None:
    """⚠ **Do not reject here** (ADR-0077 §6). Someone already linked signs in by ``sub``."""
    user = ClaimsMapping().apply({"sub": "s", "name": "誰か"})
    assert user.email is None
    assert user.subject == "s"
    assert user.username == "誰か"


def test_without_an_email_or_a_name_the_subject_becomes_the_display_name() -> None:
    """Better than creating a user with an empty display name (it can be fixed on screen later)."""
    assert ClaimsMapping().apply({"sub": "abc-123"}).username == "abc-123"


def test_the_email_domain_of_a_user_without_an_email_is_empty() -> None:
    assert ClaimsMapping().apply({"sub": "s"}).email_domain == ""


def test_groups_are_not_read_at_all() -> None:
    """⚠ **Roles are not derived from groups** (G7). assay does not issue ``groups``."""
    user = ClaimsMapping().apply({"sub": "s", "email": "a@example.com", "groups": ["admins"]})
    assert not hasattr(user, "groups")
