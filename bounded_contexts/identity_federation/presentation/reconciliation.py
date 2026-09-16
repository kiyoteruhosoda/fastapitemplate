"""定期照合の組み立て（ADR-0043）。

ユースケース（Application）と実装（Infrastructure）を結び付ける配線。
Infrastructure は Application を import できないため、組み立ては最も外側の層が行う。

**設定は実行のたびに読む。** SSO を有効にし ``MACHINE_CLIENT_ID`` を入れたら、次の周回から効く。

⚠ **走るかどうかをアプリの名乗りで決めない。** SSO が使えてサービスアカウントの `client_id` があれば
毎周回聞きに行き、assay がこのサービスアカウントをアプリの名乗りとして結び付けるまでは 403 が返る
——それを「未結び付け」として info で 1 行残し、何も変えずに終わる。

⚠ **専用のセッションを開く。** リクエストの流れの外で動くので、``get_db`` の
セッション（リクエストごとに開いて閉じる）は使えない。
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from bounded_contexts.identity_federation.application.use_cases.reconcile_federated_users import (
    ReconcileFederatedUsers,
    ReconciliationOutcome,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.domain.services.roster_gateway import (
    RosterGateway,
)
from bounded_contexts.identity_federation.infrastructure.httpx_roster_gateway import (
    HttpxRosterGateway,
)
from bounded_contexts.identity_federation.infrastructure.sql_federated_identity_repository import (
    SqlFederatedIdentityRepository,
)
from bounded_contexts.identity_federation.infrastructure.sql_session_revocation_repository import (
    SqlSessionRevocationRepository,
)
from bounded_contexts.identity_federation.presentation import dependencies
from shared.kernel.database.db import get_engine
from shared.kernel.scheduling import start_interval_worker
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)

WORKER_NAME = "sso-reconciliation"

# 照合の間隔。⚠ **設定値にしない。** 間隔は起動時に 1 回しか読まれないので、画面に出すと
# 「変えても効かない設定」になる。止まった人を拾う速さの本線は受け口（ADR-0036）で、
# こちらは取りこぼしを拾う 2 段目なので、1 時間で足りる。
RECONCILE_INTERVAL_SECONDS = 60 * 60

#: プロセスで 1 つ。⚠ **トークンを周回をまたいで使い回す**ため、呼ぶたびに作らない。
_ROSTER: RosterGateway = HttpxRosterGateway()

#: 見送っても何も変えていない失敗。⚠ **引けなかったことを「空」と読まない**（ADR-0043 決定 2）。
_SKIPPABLE = (IdentityProviderUnavailableError, SsoNotConfiguredError)


def reconcile_federated_users_once(roster: RosterGateway | None = None) -> None:
    """現在の設定に従って 1 回だけ照合する。

    ⚠ **assay に聞けなかったら、何も変えずに終わる**（「空」と「引けない」を混ぜない）。
    """
    provider = dependencies.identity_provider()
    if not settings.machine_client_id or provider is None or not provider.is_usable:
        # 照合しない設定なら、セッションも開かない。
        return
    session = sessionmaker(bind=get_engine())()
    try:
        outcome = _reconcile(session, provider.issuer, roster or _ROSTER)
    finally:
        session.close()
    if outcome is not None:
        logger.info(
            "sso_reconciliation_finished",
            extra={
                "checked": outcome.checked,
                "revoked": outcome.revoked,
                "unlinked": outcome.unlinked,
                "held_back": outcome.held_back,
            },
        )


def _reconcile(session: Session, issuer: str, roster: RosterGateway) -> ReconciliationOutcome | None:
    """照合して commit する。見送ったら巻き戻して ``None``。"""
    try:
        outcome = ReconcileFederatedUsers(
            # ⚠ 結び付けたときと**同じ出所**の発行者で引く。綴りが 1 文字ずれると
            #   1 件も当たらず、何も確かめないまま「異常なし」で終わる。
            issuer=issuer,
            identities=SqlFederatedIdentityRepository(session),
            revocations=SqlSessionRevocationRepository(session),
            roster=roster,
            keep_for_seconds=settings.refresh_token_expires_seconds,
        ).execute()
        session.commit()
    except MachineNotBoundToApplicationError:
        session.rollback()
        # ⚠ 準備待ちであって障害ではない。結び付けるまで毎時来るので warning にしない。
        logger.info("sso_reconciliation_not_bound")
        return None
    except _SKIPPABLE as error:
        session.rollback()
        logger.warning("sso_reconciliation_skipped", extra={"reason": type(error).__name__})
        return None
    except IntegrityError:
        # 別のワーカーが同じ周回で同じ失効を書いた（`jti` は決め打ちなので中身は同じ）。
        session.rollback()
        logger.info("sso_reconciliation_raced")
        return None
    return outcome


def start_sso_reconciliation_worker() -> None:
    """照合の定期実行を開始する（プロセスの起動処理から呼ぶ）。"""
    start_interval_worker(WORKER_NAME, reconcile_federated_users_once, RECONCILE_INTERVAL_SECONDS)


__all__ = [
    "RECONCILE_INTERVAL_SECONDS",
    "WORKER_NAME",
    "reconcile_federated_users_once",
    "start_sso_reconciliation_worker",
]
