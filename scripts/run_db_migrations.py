"""Apply DB migrations (``alembic upgrade head``).

Used from entrypoint.sh. It chdirs to the project root before running, so it works
wherever it is called from.
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
