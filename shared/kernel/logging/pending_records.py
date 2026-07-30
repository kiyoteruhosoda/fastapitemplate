"""リクエスト中に出たログ行の控え（``log`` テーブルへの書き込み待ち）。

``DbLogHandler`` は 1 行ごとに専用のコネクションで INSERT する。処理の途中でこれを
やると、**リクエストのセッションが握った書き込みロックと衝突する**（SQLite）。
既定の ``sqlite:///app.db`` では busy timeout（5 秒）待った末に失敗し、ハンドラが
例外を握りつぶすため「1 行のログ出力に 5 秒かかった上に DB には残らない」ことになる。

そこで処理の途中では行をここに溜め、リクエストの処理が終わってからまとめて書く
（監査ログと同じ組み立て。ADR-0013）。ミドルウェアの外（起動時処理・スクリプト）は
ロックを握る相手がいないので、その場で書く。
"""

from __future__ import annotations

from contextvars import ContextVar

# 書き込む 1 行（列名 -> 値）。ハンドラが組み立て、まとめ書きがそのまま INSERT する。
LogRow = dict[str, object]


class PendingLogRecords:
    """1 リクエスト分の控え。"""

    def __init__(self) -> None:
        self._rows: list[LogRow] = []

    def add(self, row: LogRow) -> None:
        self._rows.append(row)

    def drain(self) -> tuple[LogRow, ...]:
        """控えを取り出して空にする（二重書き込みを防ぐ）。"""
        rows = tuple(self._rows)
        self._rows.clear()
        return rows


_pending_records_var: ContextVar[PendingLogRecords | None] = ContextVar("pending_log_records", default=None)


def install_pending_log_records() -> PendingLogRecords:
    """このリクエストの控えを用意して返す（ミドルウェアが最初に呼ぶ）。"""
    pending = PendingLogRecords()
    _pending_records_var.set(pending)
    return pending


def current_pending_log_records() -> PendingLogRecords | None:
    """処理中のリクエストの控え。リクエスト外では ``None``（その場で書く）。"""
    return _pending_records_var.get()


__all__ = [
    "LogRow",
    "PendingLogRecords",
    "current_pending_log_records",
    "install_pending_log_records",
]
