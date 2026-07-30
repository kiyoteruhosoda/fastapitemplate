"""アプリログの検索インターフェース（実装は Infrastructure 層）。

書き込み側のインターフェースは持たない。``log`` テーブルへの書き込みは
:mod:`shared.kernel.logging` のハンドラが担うため（本コンテキストは読むだけ）。
"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.audit.domain.entities.application_log_entry import (
    ApplicationLogPage,
)
from bounded_contexts.audit.domain.value_objects.log_search_criteria import (
    ApplicationLogCriteria,
)


class ApplicationLogQuery(Protocol):
    def search(self, criteria: ApplicationLogCriteria) -> ApplicationLogPage:
        """*criteria* に一致する行を新しい順に 1 ページ返す（総件数付き）。"""


__all__ = ["ApplicationLogQuery"]
