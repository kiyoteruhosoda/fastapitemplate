"""権限を動かす操作の規則（ADR-0051）。"""

from shared.domain.auth.authority import beyond, changed


def test_nothing_is_beyond_when_the_actor_holds_everything() -> None:
    assert beyond({"user:manage", "item:view"}, ["item:view"]) == frozenset()


def test_codes_the_actor_lacks_are_beyond() -> None:
    assert beyond({"user:manage"}, ["user:manage", "role:manage"]) == {"role:manage"}


def test_changed_counts_both_granting_and_revoking() -> None:
    assert changed({"a", "b"}, {"b", "c"}) == {"a", "c"}


def test_nothing_changed() -> None:
    assert changed({"a"}, ["a"]) == frozenset()
