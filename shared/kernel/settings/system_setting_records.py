"""``system_settings`` テーブルの JSON レコード読み取り。

``settings`` の DB 上書き層（:mod:`shared.kernel.settings.settings`）と再起動
要求ストア（:mod:`shared.kernel.restart.request`）は、どちらも「リクエストの
外側から ``system_settings`` の 1 行を読む」という同じ事情を抱える。読み取りは
**専用の短命コネクション**で行う必要がある——共有セッションを使うと、監視
スレッドや設定解決がリクエスト側のトランザクション状態を汚してしまうため。

同じ生 SQL を両者が持たないよう、ここへ集約する。書き込みは通常の
ORM セッション（リクエスト内）で行うため、ここには読み取りだけを置く。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

_SELECT_SETTING_JSON = text("SELECT setting_json FROM system_settings WHERE setting_key = :key")


class SystemSettingRecordReader:
    """``system_settings`` の 1 行を短命コネクションで読む。"""

    @staticmethod
    def read_json(setting_key: str) -> Any | None:
        """*setting_key* の ``setting_json`` を返す。行が無ければ ``None``。

        DB 未接続・テーブル未作成（マイグレーション前）は例外として伝播する。
        「値なし」と「読めなかった」を呼び出し側が区別できるようにするため、
        ここでは握り潰さない。
        """
        from shared.kernel.database.db import get_engine

        with get_engine().connect() as connection:
            row = connection.execute(_SELECT_SETTING_JSON, {"key": setting_key}).first()
        if row is None:
            return None
        value = row[0]
        # MariaDB の JSON カラムはドライバによって文字列で返る
        return json.loads(value) if isinstance(value, str) else value


__all__ = ["SystemSettingRecordReader"]
