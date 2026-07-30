"""DB マイグレーション適用（``alembic upgrade head``）。

entrypoint.sh・deploy.sh から共用する。プロジェクトルートへ chdir してから
実行するため、どこから呼んでも動く。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    os.chdir(PROJECT_ROOT)

    from dotenv import load_dotenv

    load_dotenv()

    from alembic import command
    from alembic.config import Config

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    print("DB migrations applied (alembic upgrade head).")


if __name__ == "__main__":
    main()
