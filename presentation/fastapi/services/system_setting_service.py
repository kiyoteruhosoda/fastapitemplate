"""システム設定の読み書き（管理画面 Config が使用する）。

保存後は ``settings.reload_db_overrides()`` で即時反映する。ただし起動時にしか
読まれない設定（``restart_scopes`` 付き）はプロセスを再起動するまで効かないため、
保存結果として「どの設定がどのサービスの再起動を要するか」を返す。
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from presentation.fastapi.admin.system_settings_definitions import (
    SYSTEM_SETTING_DEFINITIONS,
    SYSTEM_SETTING_DEFINITIONS_BY_KEY,
)
from shared.infrastructure.models import SystemSetting
from shared.kernel.restart import ALL_RESTART_SCOPES, RestartScope
from shared.kernel.settings.settings import settings
from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

_SETTING_KEY = "app.config"
_SECRET_PLACEHOLDER = "********"


@dataclass(frozen=True)
class RestartRequirement:
    """保存した設定のうち、反映に再起動が要るもの。"""

    scopes: tuple[RestartScope, ...]
    keys: tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.keys)


class SystemSettingService:
    @staticmethod
    def stored_payload(session: Session) -> dict[str, Any]:
        row = session.get(SystemSetting, _SETTING_KEY)
        return dict(row.setting_json) if row and isinstance(row.setting_json, dict) else {}

    @classmethod
    def effective_config(cls, session: Session, env: Any = None) -> list[dict[str, Any]]:
        """管理画面向けに、定義・現在値・上書き状態を返す。"""
        env = os.environ if env is None else env
        stored = cls.stored_payload(session)
        result = []
        for definition in SYSTEM_SETTING_DEFINITIONS:
            key = str(definition["key"])
            value = settings.resolve(key)
            if definition.get("secret") and value:
                value = _SECRET_PLACEHOLDER
            result.append(
                {
                    **definition,
                    "value": value,
                    "env_locked": bool(env.get(key)),
                    "stored": key in stored,
                    "default": DEFAULT_APPLICATION_SETTINGS.get(key),
                }
            )
        return result

    @classmethod
    def save(cls, session: Session, values: Mapping[str, Any]) -> RestartRequirement:
        """編集可能なキーのみを保存する。未知のキーは黙って捨てる。

        戻り値は、保存したキーのうち反映に再起動が必要なものの一覧。
        """
        payload = cls.stored_payload(session)
        changed: list[str] = []
        for key, value in values.items():
            definition = SYSTEM_SETTING_DEFINITIONS_BY_KEY.get(key)
            if definition is None:
                continue
            # 伏せ字をそのまま送り返されても実値を壊さない
            if definition.get("secret") and value == _SECRET_PLACEHOLDER:
                continue
            if value is None:
                payload.pop(key, None)
            else:
                payload[key] = value
            changed.append(key)

        row = session.get(SystemSetting, _SETTING_KEY)
        if row is None:
            session.add(SystemSetting(setting_key=_SETTING_KEY, setting_json=payload))
        else:
            row.setting_json = payload
        session.flush()
        settings.reload_db_overrides()
        return cls.restart_requirement(changed)

    @staticmethod
    def restart_requirement(keys: Iterable[str]) -> RestartRequirement:
        """*keys* のうち、反映に再起動が必要なものと対象サービスを返す。"""
        affected: list[str] = []
        scopes: set[RestartScope] = set()
        for key in sorted(set(keys)):
            definition = SYSTEM_SETTING_DEFINITIONS_BY_KEY.get(key)
            if definition is None:
                continue
            # 定義は dict[str, object] なので、Iterable として扱える形に絞ってから渡す
            raw_scopes = definition.get("restart_scopes")
            scope_values: Iterable[object] = raw_scopes if isinstance(raw_scopes, list | tuple) else ()
            parsed = RestartScope.parse_all(scope_values)
            if not parsed:
                continue
            affected.append(key)
            scopes.update(parsed)
        ordered = tuple(scope for scope in ALL_RESTART_SCOPES if scope in scopes)
        return RestartRequirement(scopes=ordered, keys=tuple(affected))


__all__ = ["RestartRequirement", "SystemSettingService"]
