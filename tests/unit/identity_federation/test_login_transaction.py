"""往復状態の照合（ADR-0025）。"""

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
    """空の ``state`` で通ると、パラメータを落とすだけで照合を外せてしまう。"""
    assert not _transaction().matches("")
