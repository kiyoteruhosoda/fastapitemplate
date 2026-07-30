"""アプリケーション設定の一元アクセス。

設定値は必ずこのモジュールの :data:`settings`（:class:`ApplicationSettings`）の
``@property`` 経由で取得する。``os.getenv`` や DB への直接アクセスは禁止
（CLAUDE.md「設定管理」参照）。

優先順位: **環境変数 > DB（system_settings テーブル）> デフォルト値**。

テストでは ``ApplicationSettings(env=...)`` を個別に生成して検証できる。
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS


class _DatabaseOverrides:
    """優先順位「環境変数 > DB > デフォルト値」の DB 層。

    管理画面から保存される ``system_settings`` テーブルの ``app.config``
    レコードを供給する。

    - DB 未接続・テーブル未作成（マイグレーション前）の場面では黙って値なしを
      返し、環境変数とデフォルト値のみで動作を続ける。
    - リクエスト毎の DB アクセスを避けるため TTL キャッシュを持つ。管理画面の
      保存時は ``SystemSettingService`` が ``invalidate()`` を呼び即時反映する。
    - 読み取りは専用の短命コネクションで行う（共有セッションの
      トランザクション状態を汚さない）。
    """

    _SETTING_KEY = "app.config"
    _TTL_SECONDS = 10.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loading = threading.local()
        self._payload: dict[str, Any] = {}
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._payload = {}
        self._expires_at = 0.0

    def get(self, key: str) -> Any:
        if key not in DEFAULT_APPLICATION_SETTINGS:
            # DB 上書き対象は管理画面で編集可能なキーのみ。DATABASE_URI 等の
            # ブートストラップ用キーをここで解決すると再帰する。
            return None
        if getattr(self._loading, "active", False):
            return None
        if time.monotonic() >= self._expires_at:
            with self._lock:
                if time.monotonic() >= self._expires_at:
                    self._refresh()
        return self._payload.get(key)

    def _refresh(self) -> None:
        self._loading.active = True
        try:
            payload = self._load_payload()
            if payload is not None:
                self._payload = payload
        except Exception:
            # 直近の正常値を保持したまま、次の TTL まで再試行しない
            pass
        finally:
            self._loading.active = False
            self._expires_at = time.monotonic() + self._TTL_SECONDS

    def _load_payload(self) -> dict[str, Any] | None:
        from shared.kernel.settings.system_setting_records import (
            SystemSettingRecordReader,
        )

        value = SystemSettingRecordReader.read_json(self._SETTING_KEY)
        if value is None:
            return {}
        return value if isinstance(value, dict) else {}


class ApplicationSettings:
    """環境変数・DB・デフォルト値を統合して設定値を返す。"""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env: Mapping[str, str] = os.environ if env is None else env
        self._db = _DatabaseOverrides()

    # ------------------------------------------------------------------
    # 解決ロジック
    # ------------------------------------------------------------------

    def _get(self, key: str, default: Any = None) -> Any:
        env_value = self._env.get(key)
        if env_value is not None and env_value != "":
            return env_value
        db_value = self._db.get(key)
        if db_value is not None:
            return db_value
        return DEFAULT_APPLICATION_SETTINGS.get(key, default)

    def resolve(self, key: str, default: Any = None) -> Any:
        """キーを優先順位どおりに解決する（管理画面の現在値表示用）。

        通常のコードは型付きの ``@property`` を使うこと。
        """
        return self._get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self._get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_int(self, key: str, default: int = 0) -> int:
        value = self._get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_list(self, key: str) -> Sequence[str]:
        value = self._get(key, [])
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                value = [v.strip() for v in value.split(",") if v.strip()]
        return list(value) if isinstance(value, (list, tuple)) else []

    def reload_db_overrides(self) -> None:
        """DB 上書きキャッシュを破棄する（設定保存直後・テスト後始末用）。"""
        self._db.invalidate()

    # ------------------------------------------------------------------
    # ブートストラップ（環境変数のみ。DB 上書き対象外）
    # ------------------------------------------------------------------

    @property
    def testing(self) -> bool:
        return self.get_bool("TESTING", False)

    @property
    def database_uri(self) -> str:
        return self._env.get("DATABASE_URI") or "sqlite:///app.db"

    @property
    def admin_initial_password(self) -> str | None:
        return self._env.get("ADMIN_INITIAL_PASSWORD") or None

    # ------------------------------------------------------------------
    # 認証
    # ------------------------------------------------------------------

    @property
    def secret_key(self) -> str:
        return str(self._get("SECRET_KEY"))

    @property
    def jwt_secret_key(self) -> str:
        return str(self._get("JWT_SECRET_KEY"))

    @property
    def access_token_issuer(self) -> str:
        return str(self._get("ACCESS_TOKEN_ISSUER"))

    @property
    def access_token_audience(self) -> str:
        return str(self._get("ACCESS_TOKEN_AUDIENCE"))

    @property
    def access_token_expires_seconds(self) -> int:
        return self.get_int("ACCESS_TOKEN_EXPIRES_SECONDS", 900)

    @property
    def refresh_token_expires_seconds(self) -> int:
        return self.get_int("REFRESH_TOKEN_EXPIRES_SECONDS", 14 * 24 * 3600)

    @property
    def session_cookie_secure(self) -> bool:
        return self.get_bool("SESSION_COOKIE_SECURE", False)

    @property
    def password_reset_token_ttl_seconds(self) -> int:
        return self.get_int("PASSWORD_RESET_TOKEN_TTL_SECONDS", 3600)

    # ------------------------------------------------------------------
    # 二要素認証（TOTP）
    # ------------------------------------------------------------------

    @property
    def totp_issuer(self) -> str:
        return str(self._get("TOTP_ISSUER"))

    @property
    def totp_valid_window(self) -> int:
        return self.get_int("TOTP_VALID_WINDOW", 1)

    # ------------------------------------------------------------------
    # パスキー（WebAuthn）
    # ------------------------------------------------------------------

    @property
    def webauthn_rp_id(self) -> str:
        return str(self._get("WEBAUTHN_RP_ID"))

    @property
    def webauthn_rp_name(self) -> str:
        return str(self._get("WEBAUTHN_RP_NAME"))

    @property
    def webauthn_origin(self) -> str:
        return str(self._get("WEBAUTHN_ORIGIN")).rstrip("/")

    @property
    def webauthn_challenge_ttl_seconds(self) -> int:
        return self.get_int("WEBAUTHN_CHALLENGE_TTL_SECONDS", 300)

    # ------------------------------------------------------------------
    # 一般
    # ------------------------------------------------------------------

    @property
    def app_base_url(self) -> str:
        return str(self._get("APP_BASE_URL") or "")

    @property
    def languages(self) -> Sequence[str]:
        return self.get_list("LANGUAGES")

    @property
    def default_locale(self) -> str:
        return str(self._get("DEFAULT_LOCALE"))

    @property
    def default_theme(self) -> str:
        return str(self._get("DEFAULT_THEME"))

    @property
    def cors_allowed_origins(self) -> Sequence[str]:
        return self.get_list("CORS_ALLOWED_ORIGINS")

    # ------------------------------------------------------------------
    # メール
    # ------------------------------------------------------------------

    @property
    def mail_enabled(self) -> bool:
        return self.get_bool("MAIL_ENABLED", False)

    @property
    def mail_server(self) -> str:
        return str(self._get("MAIL_SERVER"))

    @property
    def mail_port(self) -> int:
        return self.get_int("MAIL_PORT", 587)

    @property
    def mail_use_tls(self) -> bool:
        return self.get_bool("MAIL_USE_TLS", True)

    @property
    def mail_use_ssl(self) -> bool:
        return self.get_bool("MAIL_USE_SSL", False)

    @property
    def mail_username(self) -> str:
        return str(self._get("MAIL_USERNAME") or "")

    @property
    def mail_password(self) -> str:
        return str(self._get("MAIL_PASSWORD") or "")

    @property
    def mail_default_sender(self) -> str:
        return str(self._get("MAIL_DEFAULT_SENDER") or "")

    # ------------------------------------------------------------------
    # ログ
    # ------------------------------------------------------------------

    @property
    def log_level(self) -> str:
        return str(self._get("LOG_LEVEL"))

    @property
    def log_to_database(self) -> bool:
        return self.get_bool("LOG_TO_DATABASE", True)


settings = ApplicationSettings()

__all__ = ["ApplicationSettings", "settings"]
