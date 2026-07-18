"""システム設定の読み書き（管理画面 Config が使用する）。

保存後は ``settings.reload_db_overrides()`` で即時反映する。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from presentation.fastapi.admin.system_settings_definitions import (
    SYSTEM_SETTING_DEFINITIONS,
)
from shared.infrastructure.models import SystemSetting
from shared.kernel.settings.settings import settings
from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

_SETTING_KEY = "app.config"


class SystemSettingService:
    @staticmethod
    def stored_payload(session: Session) -> dict[str, Any]:
        row = session.get(SystemSetting, _SETTING_KEY)
        return dict(row.setting_json) if row and isinstance(row.setting_json, dict) else {}

    @classmethod
    def effective_config(cls, session: Session, env: Any = None) -> list[dict[str, Any]]:
        """管理画面向けに、定義・現在値・上書き状態を返す。"""
        import os

        env = os.environ if env is None else env
        stored = cls.stored_payload(session)
        result = []
        for definition in SYSTEM_SETTING_DEFINITIONS:
            key = definition["key"]
            env_locked = bool(env.get(key))
            value = settings.resolve(key)
            if definition.get("secret") and value:
                value = "********"
            result.append(
                {
                    **definition,
                    "value": value,
                    "env_locked": env_locked,
                    "stored": key in stored,
                    "default": DEFAULT_APPLICATION_SETTINGS.get(key),
                }
            )
        return result

    @classmethod
    def save(cls, session: Session, values: dict[str, Any]) -> None:
        """編集可能なキーのみを保存する。未知のキーは黙って捨てる。"""
        editable = {d["key"] for d in SYSTEM_SETTING_DEFINITIONS}
        payload = cls.stored_payload(session)
        for key, value in values.items():
            if key not in editable:
                continue
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value
        row = session.get(SystemSetting, _SETTING_KEY)
        if row is None:
            row = SystemSetting(setting_key=_SETTING_KEY, setting_json=payload)
            session.add(row)
        else:
            row.setting_json = payload
        session.flush()
        settings.reload_db_overrides()


__all__ = ["SystemSettingService"]
