"""Reading and writing system settings (used by the admin console Config).

After saving, ``settings.reload_db_overrides()`` applies them immediately. Settings read only at
startup (those with ``restart_scopes``) don't take effect until the process restarts, so the save
result reports "which settings need a restart of which services".
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
from shared.kernel.outbound_destination import DestinationRefusedError, check_host_name
from shared.kernel.restart import ALL_RESTART_SCOPES, RestartScope
from shared.kernel.settings.settings import settings
from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    ENV_ONLY_SETTINGS,
    MAX_REFRESH_TOKEN_EXPIRES_SECONDS,
)

_SETTING_KEY = "app.config"
_SECRET_PLACEHOLDER = "********"

#: Destinations holding only a host name. Kept editable in the UI, but home-network and
#: in-cluster hosts are rejected (ADR-0090).
_CHECKED_HOST_SETTINGS = frozenset({"MAIL_SERVER"})


def _is_refresh_lifetime(value: Any) -> bool:
    """Whether it is a positive integer. ⚠ ``True`` is an ``int``, so exclude it first."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        return False
    try:
        return 0 < int(value) <= MAX_REFRESH_TOKEN_EXPIRES_SECONDS
    except ValueError:
        return False


class SettingRefusedError(ValueError):
    """A setting that cannot be saved. ``error`` is ``setting_env_only`` / ``invalid_destination`` /
    ``invalid_setting_value``."""

    def __init__(self, error: str, key: str) -> None:
        super().__init__(error)
        self.error = error
        self.key = key


@dataclass(frozen=True)
class RestartRequirement:
    """Saved settings that need a restart to take effect."""

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
        """Return definitions, current values and override state for the admin console."""
        env = os.environ if env is None else env
        stored = cls.stored_payload(session)
        result = []
        for definition in SYSTEM_SETTING_DEFINITIONS:
            key = str(definition["key"])
            value = settings.resolve(key)
            if definition.get("value_type") == "boolean":
                # Env values arrive as strings. If the UI converted them to booleans directly,
                # "false" would look on, so read it the same way as ``get_bool``, which drives
                # behaviour (task #828)
                value = settings.get_bool(key)
            elif definition.get("secret") and value:
                value = _SECRET_PLACEHOLDER
            result.append(
                {
                    **definition,
                    "env_only": key in ENV_ONLY_SETTINGS,
                    "value": value,
                    # ⚠ **Not a lock flag.** DB values beat env vars, so it can still be
                    #   changed from the UI when this is true. It means "this key also has an
                    #   env value = clearing the UI value falls back to it".
                    "env_fallback": bool(env.get(key)),
                    "stored": key in stored,
                    "default": DEFAULT_APPLICATION_SETTINGS.get(key),
                }
            )
        return result

    @classmethod
    def save(cls, session: Session, values: Mapping[str, Any]) -> RestartRequirement:
        """Save only editable keys. Unknown keys are silently dropped.

        Returns the saved keys that need a restart to take effect.
        Env-only keys and values failing the destination check are rejected with
        :class:`SettingRefusedError` (ADR-0090).
        """
        for key, value in values.items():
            cls._ensure_acceptable(key, value)
        payload = cls.stored_payload(session)
        changed: list[str] = []
        for key, value in values.items():
            definition = SYSTEM_SETTING_DEFINITIONS_BY_KEY.get(key)
            if definition is None:
                continue
            # Don't clobber the real value if the mask placeholder is sent back as is
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
    def _ensure_acceptable(key: str, value: Any) -> None:
        if key in ENV_ONLY_SETTINGS:
            raise SettingRefusedError("setting_env_only", key)
        if key in _CHECKED_HOST_SETTINGS and value:
            try:
                check_host_name(str(value))
            except DestinationRefusedError as error:
                raise SettingRefusedError("invalid_destination", key) from error
        # ``None`` means "delete the saved value and revert to the default"; always allowed
        if key == "REFRESH_TOKEN_EXPIRES_SECONDS" and value is not None and not _is_refresh_lifetime(value):
            raise SettingRefusedError("invalid_setting_value", key)
        if key == "REFRESH_TOKEN_SLIDING_ENABLED" and value is not None and not isinstance(value, bool):
            raise SettingRefusedError("invalid_setting_value", key)

    @staticmethod
    def restart_requirement(keys: Iterable[str]) -> RestartRequirement:
        """Return those of *keys* that need a restart, with the target services."""
        affected: list[str] = []
        scopes: set[RestartScope] = set()
        for key in sorted(set(keys)):
            definition = SYSTEM_SETTING_DEFINITIONS_BY_KEY.get(key)
            if definition is None:
                continue
            # Definitions are dict[str, object], so narrow to an Iterable before passing it on
            raw_scopes = definition.get("restart_scopes")
            scope_values: Iterable[object] = raw_scopes if isinstance(raw_scopes, list | tuple) else ()
            parsed = RestartScope.parse_all(scope_values)
            if not parsed:
                continue
            affected.append(key)
            scopes.update(parsed)
        ordered = tuple(scope for scope in ALL_RESTART_SCOPES if scope in scopes)
        return RestartRequirement(scopes=ordered, keys=tuple(affected))


__all__ = ["RestartRequirement", "SettingRefusedError", "SystemSettingService"]
