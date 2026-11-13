"""Seed master data (idempotent; safe to re-run after a deploy).

Usage::

    uv run python scripts/seed_master_data.py

The values live in ``shared/domain/auth/master_data.py``; the seeding logic is
``shared/infrastructure/master_data_seeder.py`` (shared with the migrations).
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
        # Running it by hand is for recovery, so also seat the initial admin if missing (ADR-0078 §3).
        ensure_default_admin(session, password=os.environ.get("ADMIN_INITIAL_PASSWORD") or None)
        # The initial admin is a tenant admin. Add them to the default tenant if absent (ADR-0079 §1)
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
