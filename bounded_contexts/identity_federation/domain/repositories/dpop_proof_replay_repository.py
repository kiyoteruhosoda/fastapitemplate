"""受けた DPoP の証明を鍵ごとに 1 回だけにする記録（ADR-0103。実装は Infrastructure 層）。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class DpopProofReplayRepository(Protocol):
    def record_if_unused(self, replay_key: str, retain_until: datetime) -> bool:
        """未使用なら記録して ``True``、既に記録済みなら ``False``（＝使い回し）。

        ⚠ 確かめてから書く 2 段にしない（同時に 2 本来ると両方通る）。一意キーへの挿入 1 回で決める。
        期限切れの記録はこの機会に掃除する。``retain_until`` は tz 付きの UTC。
        """
        ...


__all__ = ["DpopProofReplayRepository"]
