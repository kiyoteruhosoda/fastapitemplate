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

#: ホスト名だけを持つ通信先。画面に残すが、宅内やクラスタの内側は断る（ADR-0090）。
_CHECKED_HOST_SETTINGS = frozenset({"MAIL_SERVER"})


def _is_refresh_lifetime(value: Any) -> bool:
    """正の整数か。⚠ ``True`` は ``int`` の仲間なので先に除く。"""
    if isinstance(value, bool) or not isinstance(value, int | str):
        return False
    try:
        return 0 < int(value) <= MAX_REFRESH_TOKEN_EXPIRES_SECONDS
    except ValueError:
        return False


class SettingRefusedError(ValueError):
    """保存できない設定。``error`` は ``setting_env_only`` / ``invalid_destination`` / ``invalid_setting_value``。"""

    def __init__(self, error: str, key: str) -> None:
        super().__init__(error)
        self.error = error
        self.key = key


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
            if definition.get("value_type") == "boolean":
                # 環境変数の値は文字列のまま来る。画面がそのまま真偽に直すと "false" でも
                # オンに見えるので、動きを決める ``get_bool`` と同じ読み方で返す（task #828）
                value = settings.get_bool(key)
            elif definition.get("secret") and value:
                value = _SECRET_PLACEHOLDER
            result.append(
                {
                    **definition,
                    "env_only": key in ENV_ONLY_SETTINGS,
                    "value": value,
                    # ⚠ **止める印ではない。** DB の値が環境変数より強いので、
                    #   ここが真でも画面から変えられる。意味は「この鍵は
                    #   環境変数にも値がある＝画面の値を消すとそちらへ戻る」。
                    "env_fallback": bool(env.get(key)),
                    "stored": key in stored,
                    "default": DEFAULT_APPLICATION_SETTINGS.get(key),
                }
            )
        return result

    @classmethod
    def save(cls, session: Session, values: Mapping[str, Any]) -> RestartRequirement:
        """編集可能なキーのみを保存する。未知のキーは黙って捨てる。

        戻り値は、保存したキーのうち反映に再起動が必要なものの一覧。
        環境変数だけの鍵や宛先の検査に落ちた値は :class:`SettingRefusedError` で断る（ADR-0090）。
        """
        for key, value in values.items():
            cls._ensure_acceptable(key, value)
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
    def _ensure_acceptable(key: str, value: Any) -> None:
        if key in ENV_ONLY_SETTINGS:
            raise SettingRefusedError("setting_env_only", key)
        if key in _CHECKED_HOST_SETTINGS and value:
            try:
                check_host_name(str(value))
            except DestinationRefusedError as error:
                raise SettingRefusedError("invalid_destination", key) from error
        # ``None`` は「保存を消して既定へ戻す」で、いつでも通す
        if key == "REFRESH_TOKEN_EXPIRES_SECONDS" and value is not None and not _is_refresh_lifetime(value):
            raise SettingRefusedError("invalid_setting_value", key)
        if key == "REFRESH_TOKEN_SLIDING_ENABLED" and value is not None and not isinstance(value, bool):
            raise SettingRefusedError("invalid_setting_value", key)

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


__all__ = ["RestartRequirement", "SettingRefusedError", "SystemSettingService"]
