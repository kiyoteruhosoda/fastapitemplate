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

    from shared.infrastructure.master_data_seeder import ensure_default_admin, seed_master_data
    from shared.infrastructure.tenant_directory import seat_default_admin
    from shared.kernel.database.db import get_session_factory
    from shared.kernel.settings.settings import settings

    session = get_session_factory()()
    try:
        seed_master_data(session)
        # 手で流すときは復旧が目的なので、居なければ初期管理者も据える（ADR-0078 §3）。
        ensure_default_admin(session, password=os.environ.get("ADMIN_INITIAL_PASSWORD") or None)
        # 初期管理者はテナント管理者。既定のテナントに居なければ入れる（ADR-0079 §1）
        seat_default_admin(session, issuer=settings.oidc_issuer, client_id=settings.oidc_client_id)
        session.commit()
        print("Master data seeded.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
