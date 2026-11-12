"""assay's answer to "who may use this app now" (ADR-0077 §7).

A value mirroring exactly what idp's ADR-0057 endpoint returns. It holds only ``sub`` and status,
no profile (attribute copies are passed on every login. ADR-0077 §6).

⚠ **Unknown statuses fall to "leave alone".** If on the day assay adds a 4th status we read
"unknown = stop", **everyone is stopped**. Never stop people on an unreadable value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RosterState(Enum):
    """How one person on the roster is handled. Three kinds by **the action the RP takes** (idp ADR-0057)."""

    #: May use it now.
    ALLOWED = "allowed"
    #: In assay but can't use it now. ⚠ **Keep the binding** (if restored over there, they can sign in via SSO as is).
    BLOCKED = "blocked"
    #: Not in this assay tenant (= deleted). The binding may be dropped too.
    UNKNOWN = "unknown"
    #: ⚠ assay returned **a value we don't know**, or not on the roster. Do nothing.
    UNRECOGNISED = ""

    @classmethod
    def of(cls, value: str) -> RosterState:
        for state in cls:
            if state is not cls.UNRECOGNISED and state.value == value:
                return state
        return cls.UNRECOGNISED

    @property
    def ends_sessions(self) -> bool:
        """Whether this status means "no longer allow SSO sessions"."""
        return self in {RosterState.BLOCKED, RosterState.UNKNOWN}

    @property
    def drops_the_link(self) -> bool:
        """Whether the binding (the ``federated_identities`` row) may be dropped too.

        ⚠ **Don't drop the binding of someone merely suspended.** Dropping it would force them to bind
        again when restored over there (per ADR-0077 §5, only the person can create it).
        """
        return self is RosterState.UNKNOWN


@dataclass(frozen=True)
class RosterEntry:
    """One roster row."""

    subject: str
    state: RosterState

    @classmethod
    def of(cls, payload: dict[str, object]) -> RosterEntry | None:
        """Build from one element of the response. ``None`` if ``sub`` can't be read."""
        subject = payload.get("sub")
        state = payload.get("state")
        if not isinstance(subject, str) or not subject:
            return None
        return cls(subject=subject, state=RosterState.of(state if isinstance(state, str) else ""))


@dataclass(frozen=True)
class Roster:
    """The roster received in one query.

    ⚠ **Don't represent "couldn't fetch" with this type.** On failure stop with an exception and
    skip the reconciliation itself — if it became indistinguishable from an empty roster, everyone
    would be stopped just because assay is unwell (ADR-0077 §7).
    """

    entries: tuple[RosterEntry, ...]

    def state_of(self, subject: str) -> RosterState:
        """Status of that ``sub``. ⚠ **A `sub` not on the roster is `UNRECOGNISED`** (= leave alone)."""
        for entry in self.entries:
            if entry.subject == subject:
                return entry.state
        return RosterState.UNRECOGNISED


__all__ = ["Roster", "RosterEntry", "RosterState"]
