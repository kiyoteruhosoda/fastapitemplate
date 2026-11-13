"""Reading JSON records of the ``system_settings`` table.

The DB override layer of ``settings`` (:mod:`shared.kernel.settings.settings`) and the restart
request store (:mod:`shared.kernel.restart.request`) share the same situation: "read one row of
``system_settings`` from outside a request". Reads must go through **a dedicated short-lived
connection**, because using the shared session would let the watcher thread or setting
resolution disturb the request's transaction state.

Gathered here so both do not carry the same raw SQL. Writes go through the regular ORM session
(inside a request), so only reading lives here.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

_SELECT_SETTING_JSON = text("SELECT setting_json FROM system_settings WHERE setting_key = :key")


class SystemSettingRecordReader:
    """Reads one row of ``system_settings`` over a short-lived connection."""

    @staticmethod
    def read_json(setting_key: str) -> Any | None:
        """Return the ``setting_json`` of *setting_key*, or ``None`` if there is no row.

        DB not reachable / table not created (before migrations) propagate as exceptions. They are
        not swallowed here so the caller can tell "no value" from "could not read".
        """
        from shared.kernel.database.db import get_engine

        with get_engine().connect() as connection:
            row = connection.execute(_SELECT_SETTING_JSON, {"key": setting_key}).first()
        if row is None:
            return None
        value = row[0]
        # MariaDB JSON columns come back as strings depending on the driver
        return json.loads(value) if isinstance(value, str) else value


__all__ = ["SystemSettingRecordReader"]
