"""How the assay roster is read (ADR-0077 §7). ⚠ Unreadable values never suspend anyone."""

from __future__ import annotations

import pytest

from bounded_contexts.identity_federation.domain.value_objects.roster import (
    Roster,
    RosterEntry,
    RosterState,
)


@pytest.mark.parametrize(
    ("value", "state"),
    [
        ("allowed", RosterState.ALLOWED),
        ("blocked", RosterState.BLOCKED),
        ("unknown", RosterState.UNKNOWN),
        ("suspended", RosterState.UNRECOGNISED),
        ("", RosterState.UNRECOGNISED),
    ],
)
def test_states_are_read_by_their_exact_names(value: str, state: RosterState) -> None:
    assert RosterState.of(value) is state


def test_only_blocked_and_unknown_end_sessions() -> None:
    assert {state for state in RosterState if state.ends_sessions} == {RosterState.BLOCKED, RosterState.UNKNOWN}


def test_only_unknown_drops_the_link() -> None:
    """⚠ Keep the link of someone merely suspended (do not make them relink when they return)."""
    assert {state for state in RosterState if state.drops_the_link} == {RosterState.UNKNOWN}


def test_an_entry_without_a_subject_is_ignored() -> None:
    assert RosterEntry.of({"state": "blocked"}) is None
    assert RosterEntry.of({"sub": "", "state": "blocked"}) is None


def test_an_entry_with_a_non_text_state_is_unrecognised() -> None:
    entry = RosterEntry.of({"sub": "a", "state": 3})

    assert entry == RosterEntry("a", RosterState.UNRECOGNISED)


def test_a_subject_missing_from_the_roster_is_unrecognised() -> None:
    """⚠ Not being listed does not mean "deleted"."""
    roster = Roster(entries=(RosterEntry("a", RosterState.BLOCKED),))

    assert roster.state_of("a") is RosterState.BLOCKED
    assert roster.state_of("b") is RosterState.UNRECOGNISED
