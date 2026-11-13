#!/usr/bin/env python3
"""Remove one setting saved via the UI (i.e. fall back to the env var or default).

    python scripts/unset_setting.py LOCAL_LOGIN_ENABLED
    python scripts/unset_setting.py --list

⚠ **This is the way back from a lockout.** Resolution order is **DB > env var > default**, so a
value saved in the UI cannot be overridden by an env var (ADR-0074 §1). From a state where
**the UI can't be reached** (e.g. `LOCAL_LOGIN_ENABLED` set to false and then the IdP goes down),
remove the saved value to fall back to the env var / default.

⚠ **Removes a single key only.** Deleting the whole row would reset other settings too.

⚠ **Values are never printed.** Some keys hold secrets, so only key names are shown.
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
        print(f"Keys saved via the UI ({len(stored)}):")
        for key in sorted(stored):
            print(f"  {key}")
        return 0

    key = argv[0]
    if row is None or key not in stored:
        print(f"{key} is not saved via the UI (nothing to remove).", file=sys.stderr)
        return 1

    del stored[key]
    # ⚠ **Assign a new dict.** Mutating it in place may not be detected by SQLAlchemy as a
    #   change to the JSON column.
    row.setting_json = stored
    session.commit()
    print(f"Removed the saved value of {key}. The next read falls back to the env var or default.")
    print("⚠ Keys read only at startup take effect after the process is restarted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
