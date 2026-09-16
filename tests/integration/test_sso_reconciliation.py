"""定期照合（ADR-0043）を実際の SQL で見る。

- 結び付きの列挙は発行者ごとで、並びが安定していること
- 定期実行の入口が、サービスアカウントの `client_id` が無いときは assay に聞きに行かないこと
- assay が未結び付け（403）・不調と答えたら、何も変えないこと
- 通しで、止まった人の SSO のセッションが失効し、⚠ **利用者そのものは有効なまま**であること
- 何度走らせても失効の行が増えないこと
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
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
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    FederatedIdentityRecord,
    FederatedSessionRevocationRecord,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from bounded_contexts.identity_federation.presentation import dependencies, reconciliation
from shared.infrastructure.models import User
from shared.kernel.timestamps import utcnow

_ISSUER = "https://identity.example.test/tenant"


def _user(session: Session, name: str) -> int:
    user = User(email=f"{name}@example.com", username=name, password_hash="local-password", is_active=True)
    session.add(user)
    session.flush()
    return user.id


def _link(session: Session, user_id: int, subject: str, issuer: str = _ISSUER) -> None:
    session.add(
        FederatedIdentityRecord(
            issuer=issuer, subject=subject, user_id=user_id, last_login_at=utcnow() - timedelta(minutes=5)
        )
    )
    session.commit()


class _Provider:
    issuer = _ISSUER
    is_usable = True


@dataclass
class _Roster:
    states: dict[str, RosterState] = field(default_factory=dict)
    failure: Exception | None = None
    calls: int = 0

    def fetch(self, *, subjects: tuple[str, ...]) -> Roster:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return Roster(entries=tuple(RosterEntry(s, self.states[s]) for s in subjects if s in self.states))


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHINE_CLIENT_ID", "app-machine")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRES_SECONDS", "3600")
    monkeypatch.setattr(dependencies, "identity_provider", lambda: _Provider())


def _revocations(engine: sa.Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(FederatedSessionRevocationRecord)) or 0


def _session_started_minutes_ago(subject: str) -> FederatedLogin:
    return FederatedLogin(
        session=FederatedSession(_ISSUER, subject, "sid-1"),
        started_at=utcnow() - timedelta(minutes=4),
    )


def test_links_are_listed_per_issuer_in_subject_order(db_session: Session) -> None:
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    _link(db_session, alice, "sub-b")
    _link(db_session, bob, "sub-a")
    _link(db_session, alice, "elsewhere", issuer="https://other.example.test")

    listed = SqlFederatedIdentityRepository(db_session).list_for_issuer(_ISSUER)

    assert [link.subject for link in listed] == ["sub-a", "sub-b"]
    assert all(link.last_login_at is not None for link in listed)


def test_the_job_does_not_ask_assay_without_the_machine_client(
    engine: sa.Engine, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHINE_CLIENT_ID", "")
    roster = _Roster()

    reconciliation.reconcile_federated_users_once(roster)

    assert roster.calls == 0


def test_the_job_does_not_ask_assay_while_sso_is_off(
    engine: sa.Engine, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dependencies, "identity_provider", lambda: None)
    roster = _Roster()

    reconciliation.reconcile_federated_users_once(roster)

    assert roster.calls == 0


@pytest.mark.parametrize(
    "failure",
    [MachineNotBoundToApplicationError(), IdentityProviderUnavailableError()],
    ids=["not-bound", "unavailable"],
)
def test_a_roster_we_could_not_read_changes_nothing(
    engine: sa.Engine, db_session: Session, configured: None, failure: Exception
) -> None:
    carol = _user(db_session, "carol")
    _link(db_session, carol, "sub-carol")

    reconciliation.reconcile_federated_users_once(_Roster(failure=failure))

    assert _revocations(engine) == 0
    assert SqlFederatedIdentityRepository(db_session).find(_ISSUER, "sub-carol") is not None


def test_a_stopped_user_loses_sso_sessions_but_keeps_the_local_account(
    engine: sa.Engine, db_session: Session, configured: None
) -> None:
    """⚠ この雛形はローカル口座を意図して持つ。IdP の停止でパスワードまで止めない。"""
    dave = _user(db_session, "dave")
    erin = _user(db_session, "erin")
    _link(db_session, dave, "sub-dave")
    _link(db_session, erin, "sub-erin")
    roster = _Roster(states={"sub-dave": RosterState.BLOCKED, "sub-erin": RosterState.UNKNOWN})

    reconciliation.reconcile_federated_users_once(roster)

    with Session(engine) as fresh:
        revocations = SqlSessionRevocationRepository(fresh)
        assert revocations.is_revoked(_session_started_minutes_ago("sub-dave"))
        assert revocations.is_revoked(_session_started_minutes_ago("sub-erin"))
        identities = SqlFederatedIdentityRepository(fresh)
        assert identities.find(_ISSUER, "sub-dave") is not None
        assert identities.find(_ISSUER, "sub-erin") is None
        assert [user.is_active for user in fresh.scalars(select(User).where(User.id.in_((dave, erin))))] == [True, True]


def test_running_every_hour_does_not_pile_up_rows(engine: sa.Engine, db_session: Session, configured: None) -> None:
    frank = _user(db_session, "frank")
    _link(db_session, frank, "sub-frank")
    roster = _Roster(states={"sub-frank": RosterState.BLOCKED})

    reconciliation.reconcile_federated_users_once(roster)
    reconciliation.reconcile_federated_users_once(roster)

    assert _revocations(engine) == 1
