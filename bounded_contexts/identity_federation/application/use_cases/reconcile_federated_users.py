"""assay へ聞き直して、使えなくなった人の SSO のセッションを止める（定期照合。ADR-0043）。

受け口（ADR-0036）が取りこぼしたぶんを拾う 2 段目である。止める範囲は受け口と同じ
——**SSO で始まったセッションだけ**で、利用者そのもの（ローカルのパスワード・パスキー）には
触らない。この雛形はローカル口座を意図して持つ（ADR-0039）。

⚠ **引けなかったときは何もしない。** 名簿が引けないことと、名簿が空であることを混ぜない
——混ぜると、assay が不調なだけで全員を止める。引けない場合は
:class:`~bounded_contexts.identity_federation.domain.exceptions.IdentityProviderUnavailableError`
が上がり、この仕事は何も変えずに終わる。

⚠ **何度走らせても結果が同じになるように書く。** 定期実行はワーカーの数だけ同時に走る
（ADR-0021）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime

from bounded_contexts.identity_federation.domain.entities.federated_identity import (
    FederatedIdentity,
)
from bounded_contexts.identity_federation.domain.entities.session_revocation import (
    SessionRevocation,
)
from bounded_contexts.identity_federation.domain.repositories.federated_identity_repository import (
    FederatedIdentityRepository,
)
from bounded_contexts.identity_federation.domain.repositories.session_revocation_repository import (
    SessionRevocationRepository,
)
from bounded_contexts.identity_federation.domain.services.roster_gateway import (
    RosterGateway,
)
from bounded_contexts.identity_federation.domain.value_objects.roster import (
    Roster,
    RosterState,
)
from shared.kernel.timestamps import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationOutcome:
    """1 回の照合で何が起きたか（記録と試験のための数）。"""

    checked: int = 0
    #: 新しく失効させた人数。⚠ 前の周回で失効済みの人は数えない（同じ行は書かない）。
    revoked: int = 0
    unlinked: int = 0
    #: ⚠ **全員が `unknown` で返ったので見送った**か（決定 3）。真のときは何も変えていない。
    held_back: bool = False


@dataclass(frozen=True)
class ReconcileFederatedUsers:
    issuer: str
    identities: FederatedIdentityRepository
    revocations: SessionRevocationRepository
    roster: RosterGateway
    #: 失効の記録を残す秒数。**リフレッシュトークンの寿命**を渡す（受け口と同じ。ADR-0036）。
    keep_for_seconds: int

    def execute(self) -> ReconciliationOutcome:
        links = list(self.identities.list_for_issuer(self.issuer))
        if not links:
            return ReconciliationOutcome()
        # ⚠ 名指しで聞く。候補の一覧では「向こうに居ない（消えた）」が分からない。
        answers = self.roster.fetch(subjects=tuple(link.subject for link in links))
        outcome = ReconciliationOutcome(checked=len(links))
        if _everyone_is_unknown(links, answers):
            # ⚠ テナントの取り違え・アプリの付け替えでもこの形になる。結び付きは本人の
            #   操作でしか作り直せない（ADR-0040）ので、全員分を外す前に止まる。
            logger.warning("sso_reconciliation_everyone_unknown", extra={"checked": len(links)})
            return replace(outcome, held_back=True)
        now = utcnow()
        for link in links:
            outcome = self._apply(link, answers.state_of(link.subject), now, outcome)
        return outcome

    def _apply(
        self,
        link: FederatedIdentity,
        state: RosterState,
        now: datetime,
        outcome: ReconciliationOutcome,
    ) -> ReconciliationOutcome:
        """1 人ぶんの結果を反映する。⚠ **触らない側も明示的に返す。**"""
        if not state.ends_sessions:
            return outcome
        revocation = SessionRevocation.after_reconciliation(
            link,
            now=now,
            keep_for_seconds=self.keep_for_seconds,
        )
        if self.revocations.record(revocation):
            logger.info("sso_sessions_revoked_by_reconciliation", extra={"user_id": link.user_id})
            outcome = replace(outcome, revoked=outcome.revoked + 1)
        if not state.drops_the_link:
            return outcome
        # 向こうに居ない＝結び付きの相手がもう存在しない。行を残すと、同じ `sub` が
        # 別人へ再利用されたときに他人へ繋がる（再利用しない約束だが、残す理由も無い）。
        # ⚠ 失効の記録は結び付きではなく `(issuer, sub)` に効くので、外した後も残る。
        self.identities.unlink(link)
        logger.info("sso_identity_unlinked_by_reconciliation", extra={"user_id": link.user_id})
        return replace(outcome, unlinked=outcome.unlinked + 1)


def _everyone_is_unknown(links: list[FederatedIdentity], answers: Roster) -> bool:
    """結び付きが 2 件以上あり、全員が `unknown` で返ったか（ADR-0043 決定 3）。

    1 件だけのときは「その 1 人が消えた」と区別が付かないので、通常どおり扱う。
    """
    if len(links) < 2:
        return False
    return all(answers.state_of(link.subject) is RosterState.UNKNOWN for link in links)


__all__ = ["ReconcileFederatedUsers", "ReconciliationOutcome"]
