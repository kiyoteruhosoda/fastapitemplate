"""ログの保持期間。

``log`` と ``audit_log`` は性質が違うので日数を別に持つ（ADR-0021）。アプリログは
多い・短命で削ってよいが、監査ログは「誰が何をしたか」の記録で、消してよい行が無い。

``0`` は「削除しない」。保持期間は運用・監査の要件で決まるもので、テンプレートが
既定で消し始めてよいものではないため、既定はどちらも ``0``。負の日数も同じ扱いに
する（設定の打ち間違いで直近の行まで消さない）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

KEEP_FOREVER = 0


@dataclass(frozen=True, slots=True)
class LogRetentionPolicy:
    """どのテーブルを何日残すか。"""

    application_log_days: int = KEEP_FOREVER
    audit_log_days: int = KEEP_FOREVER

    @property
    def purges_nothing(self) -> bool:
        """どちらのテーブルも削除対象にならないか。"""
        return self.application_log_days <= KEEP_FOREVER and self.audit_log_days <= KEEP_FOREVER

    def application_log_cutoff(self, now: datetime) -> datetime | None:
        """これより古いアプリログを消す境界。削除しない設定なら ``None``。"""
        return _cutoff(self.application_log_days, now)

    def audit_log_cutoff(self, now: datetime) -> datetime | None:
        """これより古い監査ログを消す境界。削除しない設定なら ``None``。"""
        return _cutoff(self.audit_log_days, now)


def _cutoff(days: int, now: datetime) -> datetime | None:
    if days <= KEEP_FOREVER:
        return None
    return now - timedelta(days=days)


__all__ = ["KEEP_FOREVER", "LogRetentionPolicy"]
