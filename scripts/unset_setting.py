#!/usr/bin/env python3
"""画面で保存した設定を 1 つ消す（＝環境変数か既定値へ戻す）。

    python scripts/unset_setting.py LOCAL_LOGIN_ENABLED
    python scripts/unset_setting.py --list

⚠ **締め出しからの戻り道である。** 解決の順序は **DB > 環境変数 > 既定値** なので、
画面で保存した値は環境変数では上書きできない（ADR-0034）。`LOCAL_LOGIN_ENABLED`
を偽にしたまま IdP が落ちる、のような**画面に入れない状態**からは、保存を消して
環境変数・既定値へ戻す。

⚠ **消すのは 1 鍵だけ。** 行ごと削ると、他の設定まで既定へ戻る。

⚠ **値は出さない。** 秘密が入っている鍵もあるので、出すのは鍵の名前だけである。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.infrastructure.models import SystemSetting
from shared.kernel.database.session import get_db

_SETTING_KEY = "app.config"


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    session = next(get_db())
    row = session.get(SystemSetting, _SETTING_KEY)
    stored = dict(row.setting_json) if row and isinstance(row.setting_json, dict) else {}

    if argv[0] == "--list":
        print(f"画面で保存されている鍵（{len(stored)} 件）:")
        for key in sorted(stored):
            print(f"  {key}")
        return 0

    key = argv[0]
    if row is None or key not in stored:
        print(f"{key} は画面で保存されていない（消すものが無い）。", file=sys.stderr)
        return 1

    del stored[key]
    # ⚠ **新しい dict を代入する。** 中身を書き換えるだけでは JSON 列の変更を
    #   SQLAlchemy が拾わないことがある。
    row.setting_json = stored
    session.commit()
    print(f"{key} の保存を消した。次に読むときは環境変数か既定値へ戻る。")
    print("⚠ 起動時にしか読まれない鍵は、プロセスを起こし直すまで効かない。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
