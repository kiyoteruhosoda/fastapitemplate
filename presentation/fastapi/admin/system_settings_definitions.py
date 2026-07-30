"""管理画面（Config）の設定項目定義。

キーを追加したら ``system_settings_defaults.py`` と ``settings.py`` も更新する
（CLAUDE.md「設定管理」参照）。

各項目のキー:

- ``key`` / ``category`` / ``value_type``: 必須。
- ``label``: 英語の既定ラベル。表示文言の翻訳はフロントエンド側で行う
  （``config.field.<KEY>`` を辞書に持たせ、無ければこのラベルを使う）。
- ``secret``: 画面へ値を返さない（``********`` に伏せる）。
- ``choices``: 選択肢を持つ項目。値と表示用ラベルの組。
- ``restart_scopes``: **起動時にしか読まれない**設定に付ける。保存時に管理画面が
  「再起動が必要」と提示し、そこから再起動を要求できる
  （:mod:`shared.kernel.restart`）。空なら保存と同時に反映される。
"""

from __future__ import annotations

from shared.kernel.restart import RestartScope

# 起動時にしか読まれない設定（アプリケーションファクトリで一度だけ評価される）
_RESTART_WEB: tuple[str, ...] = (RestartScope.WEB.value,)

SYSTEM_SETTING_DEFINITIONS: list[dict[str, object]] = [
    # --- 認証 ---
    {
        "key": "ACCESS_TOKEN_EXPIRES_SECONDS",
        "category": "auth",
        "label": "Access token lifetime (seconds)",
        "value_type": "integer",
    },
    {
        "key": "REFRESH_TOKEN_EXPIRES_SECONDS",
        "category": "auth",
        "label": "Refresh token lifetime (seconds)",
        "value_type": "integer",
    },
    {
        "key": "SESSION_COOKIE_SECURE",
        "category": "auth",
        "label": "Secure cookie (HTTPS only)",
        "value_type": "boolean",
    },
    {
        "key": "PASSWORD_RESET_TOKEN_TTL_SECONDS",
        "category": "auth",
        "label": "Password reset token TTL (seconds)",
        "value_type": "integer",
    },
    # --- 二要素認証（TOTP） ---
    {
        "key": "TOTP_ISSUER",
        "category": "two_factor",
        "label": "Issuer shown in authenticator apps",
        "value_type": "string",
    },
    {
        "key": "TOTP_VALID_WINDOW",
        "category": "two_factor",
        "label": "Accepted time-step drift",
        "value_type": "integer",
    },
    # --- パスキー（WebAuthn） ---
    {"key": "WEBAUTHN_RP_ID", "category": "passkey", "label": "Relying party ID (domain)", "value_type": "string"},
    {"key": "WEBAUTHN_RP_NAME", "category": "passkey", "label": "Relying party name", "value_type": "string"},
    {"key": "WEBAUTHN_ORIGIN", "category": "passkey", "label": "Expected browser origin", "value_type": "string"},
    {
        "key": "WEBAUTHN_CHALLENGE_TTL_SECONDS",
        "category": "passkey",
        "label": "Challenge lifetime (seconds)",
        "value_type": "integer",
    },
    # --- 一般 ---
    {"key": "APP_BASE_URL", "category": "general", "label": "Application base URL", "value_type": "string"},
    {"key": "LANGUAGES", "category": "general", "label": "Selectable languages", "value_type": "list"},
    {
        "key": "DEFAULT_LOCALE",
        "category": "general",
        "label": "Default locale",
        "value_type": "string",
        "choices": [["en", "English"], ["ja", "日本語"]],
    },
    {
        "key": "DEFAULT_THEME",
        "category": "general",
        "label": "Default theme",
        "value_type": "string",
        "choices": [["system", "Follow the OS"], ["light", "Light"], ["dark", "Dark"]],
    },
    {
        "key": "CORS_ALLOWED_ORIGINS",
        "category": "general",
        "label": "CORS allowed origins",
        "value_type": "list",
        "restart_scopes": _RESTART_WEB,
    },
    # --- メール ---
    {"key": "MAIL_ENABLED", "category": "mail", "label": "Enable mail sending", "value_type": "boolean"},
    {"key": "MAIL_SERVER", "category": "mail", "label": "SMTP server", "value_type": "string"},
    {"key": "MAIL_PORT", "category": "mail", "label": "SMTP port", "value_type": "integer"},
    {"key": "MAIL_USE_TLS", "category": "mail", "label": "Use STARTTLS", "value_type": "boolean"},
    {"key": "MAIL_USE_SSL", "category": "mail", "label": "Use SSL", "value_type": "boolean"},
    {"key": "MAIL_USERNAME", "category": "mail", "label": "SMTP username", "value_type": "string"},
    {"key": "MAIL_PASSWORD", "category": "mail", "label": "SMTP password", "value_type": "string", "secret": True},
    {"key": "MAIL_DEFAULT_SENDER", "category": "mail", "label": "Default sender address", "value_type": "string"},
    # --- ログ ---
    {
        "key": "LOG_LEVEL",
        "category": "logging",
        "label": "Log level",
        "value_type": "string",
        "choices": [["DEBUG", "DEBUG"], ["INFO", "INFO"], ["WARNING", "WARNING"], ["ERROR", "ERROR"]],
        "restart_scopes": _RESTART_WEB,
    },
    {
        "key": "LOG_TO_DATABASE",
        "category": "logging",
        "label": "Write logs to database",
        "value_type": "boolean",
        "restart_scopes": _RESTART_WEB,
    },
]

SYSTEM_SETTING_DEFINITIONS_BY_KEY: dict[str, dict[str, object]] = {
    str(definition["key"]): definition for definition in SYSTEM_SETTING_DEFINITIONS
}

__all__ = ["SYSTEM_SETTING_DEFINITIONS", "SYSTEM_SETTING_DEFINITIONS_BY_KEY"]
