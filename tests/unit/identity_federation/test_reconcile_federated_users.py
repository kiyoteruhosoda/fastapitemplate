"""定期照合 ——止まった人・消えた人の SSO のセッションを止め、それ以外には触らない（ADR-0043）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from bounded_contexts.identity_federation.application.use_cases import reconcile_federated_users
from bounded_contexts.identity_federation.application.use_cases.reconcile_federated_users import (
    ReconcileFederatedUsers,
    ReconciliationOutcome,
)
from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_login import (
    FederatedLogin,
)
from bounded_contexts.identity_federation.domain.value_objects.federated_session import (
    FederatedSession,
)
from bounded_contexts.identity_federation.domain.value_objects.roster import (
    Roster,
    RosterEntry,
    RosterState,
)

_ISSUER = "https://idp.example.test/tenant"
_NOW = datetime(2026, 9, 16, 12, 0, 0)
_LOGGED_IN = _NOW - timedelta(days=1)


@dataclass
class _Identities:
    rows: list[FederatedIdentity] = field(default_factory=list)

    def find(self, issuer: str, subject: str) -> FederatedIdentity | None:
        return next((r for r in self.rows if (r.issuer, r.subject) == (issuer, subject)), None)

    def find_for_user(self, issuer: str, user_id: int) -> FederatedIdentity | None:
        return next((r for r in self.rows if r.issuer == issuer and r.user_id == user_id), None)

    def link(self, identity: FederatedIdentity) -> FederatedIdentity:
        self.rows.append(identity)
        return identity

    def unlink(self, identity: FederatedIdentity) -> None:
        self.rows.remove(identity)

    def touch(self, identity: FederatedIdentity) -> None:
        return None

    def list_for_issuer(self, issuer: str) -> list[FederatedIdentity]:
        return [r for r in self.rows if r.issuer == issuer]


@dataclass
class _Revocations:
    """``jti`` の重複を弾くところまで実物と同じにした控え。"""

    rows: dict[str, SessionRevocation] = field(default_factory=dict)

    def record(self, revocation: SessionRevocation) -> bool:
        if revocation.jti in self.rows:
            return False
        self.rows[revocation.jti] = revocation
        return True

    def is_revoked(self, login: FederatedLogin) -> bool:
        return any(row.covers(login) for row in self.rows.values())


@dataclass
class _Roster:
    states: dict[str, RosterState]
    unavailable: bool = False
    asked: list[tuple[str, ...]] = field(default_factory=list)

    def fetch(self, *, subjects: tuple[str, ...]) -> Roster:
        self.asked.append(subjects)
        if self.unavailable:
            raise IdentityProviderUnavailableError
        return Roster(entries=tuple(RosterEntry(s, self.states[s]) for s in subjects if s in self.states))


@dataclass
class _World:
    identities: _Identities
    revocations: _Revocations
    roster: _Roster

    def run(self, now: datetime = _NOW) -> ReconciliationOutcome:
        with patch.object(reconcile_federated_users, "utcnow", return_value=now):
            return ReconcileFederatedUsers(
                issuer=_ISSUER,
                identities=self.identities,
                revocations=self.revocations,
                roster=self.roster,
                keep_for_seconds=3600,
            ).execute()


def _link(subject: str, user_id: int, last_login_at: datetime = _LOGGED_IN) -> FederatedIdentity:
    return FederatedIdentity(issuer=_ISSUER, subject=subject, user_id=user_id, last_login_at=last_login_at)


def _world(states: dict[str, RosterState], *links: FederatedIdentity) -> _World:
    return _World(_Identities(list(links)), _Revocations(), _Roster(states))


def _session_of(subject: str, started_at: datetime = _LOGGED_IN) -> FederatedLogin:
    return FederatedLogin(session=FederatedSession(_ISSUER, subject, "sid-1"), started_at=started_at)


def test_nothing_is_asked_when_nobody_is_linked() -> None:
    world = _world({})

    assert world.run() == ReconciliationOutcome()
    assert world.roster.asked == []


def test_everyone_linked_is_asked_by_name() -> None:
    """⚠ 名指しで聞く。候補の一覧では「消えた」が分からない。"""
    world = _world({}, _link("a", 1), _link("b", 2))

    world.run()

    assert world.roster.asked == [("a", "b")]


def test_an_allowed_user_is_left_alone() -> None:
    world = _world({"a": RosterState.ALLOWED}, _link("a", 1))

    outcome = world.run()

    assert outcome == ReconciliationOutcome(checked=1)
    assert world.revocations.rows == {}


def test_a_blocked_user_loses_every_sso_session_but_keeps_the_link() -> None:
    """⚠ 結び付きは残す ——assay で戻れば、本人は結び付け直さずに SSO で入れる。"""
    world = _world({"a": RosterState.BLOCKED}, _link("a", 1))

    outcome = world.run()

    assert outcome == ReconciliationOutcome(checked=1, revoked=1)
    assert world.revocations.is_revoked(_session_of("a"))
    assert world.identities.find(_ISSUER, "a") is not None


def test_an_unknown_user_loses_the_sessions_and_the_link() -> None:
    world = _world({"a": RosterState.UNKNOWN}, _link("a", 1))

    outcome = world.run()

    assert outcome == ReconciliationOutcome(checked=1, revoked=1, unlinked=1)
    assert world.revocations.is_revoked(_session_of("a"))
    assert world.identities.find(_ISSUER, "a") is None


@pytest.mark.parametrize("states", [{"a": RosterState.UNRECOGNISED}, {}], ids=["unrecognised", "not-listed"])
def test_an_answer_we_cannot_read_touches_nobody(states: dict[str, RosterState]) -> None:
    """⚠ assay が 4 つ目の状態を足した日に、全員を止めない。"""
    world = _world(states, _link("a", 1))

    assert world.run() == ReconciliationOutcome(checked=1)
    assert world.revocations.rows == {}


def test_an_unreachable_roster_changes_nothing() -> None:
    """⚠ 「引けない」を「空」と読まない。"""
    world = _world({}, _link("a", 1))
    world.roster.unavailable = True

    with pytest.raises(IdentityProviderUnavailableError):
        world.run()

    assert world.revocations.rows == {}
    assert world.identities.find(_ISSUER, "a") is not None


def test_everyone_unknown_is_held_back() -> None:
    """⚠ テナントの取り違えでも全員 `unknown` になる。結び付きを全員分外す前に止まる。"""
    world = _world({"a": RosterState.UNKNOWN, "b": RosterState.UNKNOWN}, _link("a", 1), _link("b", 2))

    outcome = world.run()

    assert outcome == ReconciliationOutcome(checked=2, held_back=True)
    assert world.revocations.rows == {}
    assert len(world.identities.rows) == 2


def test_a_single_unknown_link_is_not_held_back() -> None:
    """1 件だけなら「その人が消えた」と区別が付かないので、通常どおり扱う。"""
    world = _world({"a": RosterState.UNKNOWN}, _link("a", 1))

    assert world.run().held_back is False


def test_running_again_writes_nothing_new() -> None:
    """⚠ 毎時・ワーカーの数だけ走る。同じログインに対する失効は 1 本で足りる。"""
    world = _world({"a": RosterState.BLOCKED}, _link("a", 1))

    world.run()
    second = world.run()

    assert second == ReconciliationOutcome(checked=1)
    assert len(world.revocations.rows) == 1


def test_a_user_who_came_back_and_was_stopped_again_is_stopped_again() -> None:
    """⚠ 入り直したセッションは古い失効に当たらない。新しいログインには新しい失効を書く。"""
    world = _world({"a": RosterState.BLOCKED}, _link("a", 1))
    world.run()
    came_back_at = _NOW + timedelta(hours=1)
    world.identities.rows = [_link("a", 1, last_login_at=came_back_at)]
    assert not world.revocations.is_revoked(_session_of("a", started_at=came_back_at))

    outcome = world.run(now=_NOW + timedelta(hours=2))

    assert outcome.revoked == 1
    assert world.revocations.is_revoked(_session_of("a", started_at=came_back_at))
