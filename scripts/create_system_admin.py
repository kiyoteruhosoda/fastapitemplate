"""システム管理者（テナントに属さない ``system-admin``）を 1 人作る（ADR-0079 §1・§3）。

使い方::

    SYSTEM_ADMIN_PASSWORD='…' uv run python scripts/create_system_admin.py <メールアドレス> [<表示名>]

パスワードは環境変数で渡す（引数に書くとシェルの履歴とプロセス一覧に残る）。
同じメールアドレスの利用者が居れば何もしない。2 人目からは、システム管理者が画面で足す。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

_MIN_PASSWORD_LENGTH = 12


def main(argv: list[str]) -> int:
    load_dotenv()
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    password = os.environ.get("SYSTEM_ADMIN_PASSWORD") or ""
    if len(password) < _MIN_PASSWORD_LENGTH:
        print(f"SYSTEM_ADMIN_PASSWORD を {_MIN_PASSWORD_LENGTH} 文字以上で渡してください。")
        return 2

    from shared.infrastructure.system_administrators import create_system_administrator
    from shared.kernel.database.db import get_session_factory

    email = argv[1]
    username = argv[2] if len(argv) == 3 else email.split("@")[0]
    session = get_session_factory()()
    try:
        created = create_system_administrator(session, email=email, username=username, password=password)
        session.commit()
    finally:
        session.close()
    print("System administrator created." if created else "A user with that email already exists; nothing changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
