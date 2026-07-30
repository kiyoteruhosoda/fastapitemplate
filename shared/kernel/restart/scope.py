"""再起動の対象範囲（スコープ）。

設定値ごとに「どのサービスを再起動すれば反映されるか」を表す語彙。
``docker-compose.yml`` のアプリケーションサービスと 1 対 1 で対応する。

本テンプレートのサービスは ``web`` のみ。バックグラウンドワーカー等を足した
場合はここへ値を追加し、そのプロセスの起動処理で
:func:`shared.kernel.restart.start_restart_watcher` を呼ぶ。
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class RestartScope(StrEnum):
    """再起動要求の宛先となるサービス。"""

    WEB = "web"

    @classmethod
    def parse(cls, value: object) -> RestartScope | None:
        """文字列をスコープへ変換する。未知の値は ``None``。"""
        if isinstance(value, RestartScope):
            return value
        if not isinstance(value, str):
            return None
        normalised = value.strip().lower()
        return next((scope for scope in cls if scope.value == normalised), None)

    @classmethod
    def parse_all(cls, values: Iterable[object]) -> tuple[RestartScope, ...]:
        """文字列の並びをスコープの並びへ変換する（未知の値は捨てる）。

        並び順は :data:`ALL_RESTART_SCOPES` に揃え、重複は取り除く。
        """
        parsed = {scope for scope in (cls.parse(value) for value in values) if scope is not None}
        return tuple(scope for scope in ALL_RESTART_SCOPES if scope in parsed)


ALL_RESTART_SCOPES: tuple[RestartScope, ...] = tuple(RestartScope)


__all__ = ["ALL_RESTART_SCOPES", "RestartScope"]
