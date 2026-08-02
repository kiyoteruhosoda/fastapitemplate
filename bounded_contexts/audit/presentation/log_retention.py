"""保持期間を過ぎたログの掃除（定期実行の組み立て）。

ユースケース（Application）と削除の実装（Infrastructure）を結び付ける配線。
Infrastructure は Application を import できないため、組み立ては最も外側の層が行う。

**設定は実行のたびに読む。** 管理画面で保持日数を変えたら次の周回から効く
（再起動は要らない ＝ 設定定義に ``restart_scopes`` を付けていない）。
"""

from __future__ import annotations

from bounded_contexts.audit.application.use_cases.purge_expired_logs import (
    PurgeExpiredLogs,
)
from bounded_contexts.audit.domain.value_objects.retention_policy import (
    LogRetentionPolicy,
)
from bounded_contexts.audit.infrastructure.sql_expired_log_remover import (
    SqlExpiredLogRemover,
)
from shared.kernel.scheduling import start_interval_worker
from shared.kernel.timestamps import utcnow

WORKER_NAME = "log-retention"

# 掃除の間隔。保持期間は日単位なので、1 日に数回見れば十分（設定値にはしない。
# 運用者が決めるのは「何日残すか」であって「何秒ごとに見るか」ではない）。
PURGE_INTERVAL_SECONDS = 6 * 60 * 60


def purge_expired_logs_once() -> None:
    """現在の設定に従って 1 回だけ掃除する。"""
    from shared.kernel.settings.settings import settings

    policy = LogRetentionPolicy(
        application_log_days=settings.log_retention_days,
        audit_log_days=settings.audit_log_retention_days,
    )
    PurgeExpiredLogs(SqlExpiredLogRemover()).execute(policy, utcnow())


def start_log_retention_worker() -> None:
    """掃除の定期実行を開始する（プロセスの起動処理から呼ぶ）。"""
    start_interval_worker(WORKER_NAME, purge_expired_logs_once, PURGE_INTERVAL_SECONDS)


__all__ = ["PURGE_INTERVAL_SECONDS", "WORKER_NAME", "purge_expired_logs_once", "start_log_retention_worker"]
