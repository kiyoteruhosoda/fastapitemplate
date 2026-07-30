"""マスタデータ投入スクリプト（冪等・デプロイ後の再実行可）。

使い方::

    uv run python scripts/seed_master_data.py

値の正本は ``shared/domain/auth/master_data.py``、投入ロジックは
``shared/infrastructure/master_data_seeder.py``（マイグレーションと共用）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    from shared.infrastructure.master_data_seeder import seed_master_data
    from shared.kernel.database.db import get_session_factory

    session = get_session_factory()()
    try:
        seed_master_data(session, admin_password=os.environ.get("ADMIN_INITIAL_PASSWORD") or None)
        session.commit()
        print("Master data seeded.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
