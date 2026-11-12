"""Matching the round-trip state (ADR-0077 §1)."""

from __future__ import annotations

from bounded_contexts.identity_federation.domain.value_objects.login_transaction import (
    LoginTransaction,
)


def _transaction(state: str = "st") -> LoginTransaction:
    return LoginTransaction(state=state, nonce="no", code_verifier="cv", redirect_to="/")


def test_matches_only_the_state_it_sent() -> None:
    assert _transaction().matches("st")
    assert not _transaction().matches("other")


def test_an_empty_state_never_matches() -> None:
    """If an empty ``state`` passed, dropping the parameter would be enough to bypass the check."""
    assert not _transaction().matches("")


def test_belongs_only_to_the_issuer_it_was_sent_to() -> None:
    """A round trip without an issuer (from before tenants) belongs to no issuer (ADR-0079 §4)."""
    sent = LoginTransaction(state="st", nonce="no", code_verifier="cv", issuer="https://a.example")
    assert sent.is_for("https://a.example")
    assert not sent.is_for("https://b.example")
    assert not _transaction().is_for("https://a.example")
