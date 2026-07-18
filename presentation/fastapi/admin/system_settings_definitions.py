"""管理画面（Config）の設定項目定義。

キーを追加したら ``system_settings_defaults.py`` と ``settings.py`` も更新する
（CLAUDE.md「設定管理」参照）。``secret: True`` の項目は画面へ値を返さない。
"""
from __future__ import annotations

SYSTEM_SETTING_DEFINITIONS: list[dict[str, object]] = [
    # --- 認証 ---
    {"key": "ACCESS_TOKEN_EXPIRES_SECONDS", "category": "auth",
     "label": "Access token lifetime (seconds)", "value_type": "integer"},
    {"key": "REFRESH_TOKEN_EXPIRES_SECONDS", "category": "auth",
     "label": "Refresh token lifetime (seconds)", "value_type": "integer"},
    {"key": "SESSION_COOKIE_SECURE", "category": "auth",
     "label": "Secure cookie (HTTPS only)", "value_type": "boolean"},
    {"key": "PASSWORD_RESET_TOKEN_TTL_SECONDS", "category": "auth",
     "label": "Password reset token TTL (seconds)", "value_type": "integer"},
    # --- 一般 ---
    {"key": "APP_BASE_URL", "category": "general",
     "label": "Application base URL", "value_type": "string"},
    {"key": "DEFAULT_LOCALE", "category": "general",
     "label": "Default locale", "value_type": "string"},
    {"key": "CORS_ALLOWED_ORIGINS", "category": "general",
     "label": "CORS allowed origins", "value_type": "list"},
    # --- メール ---
    {"key": "MAIL_ENABLED", "category": "mail",
     "label": "Enable mail sending", "value_type": "boolean"},
    {"key": "MAIL_SERVER", "category": "mail",
     "label": "SMTP server", "value_type": "string"},
    {"key": "MAIL_PORT", "category": "mail",
     "label": "SMTP port", "value_type": "integer"},
    {"key": "MAIL_USE_TLS", "category": "mail",
     "label": "Use STARTTLS", "value_type": "boolean"},
    {"key": "MAIL_USE_SSL", "category": "mail",
     "label": "Use SSL", "value_type": "boolean"},
    {"key": "MAIL_USERNAME", "category": "mail",
     "label": "SMTP username", "value_type": "string"},
    {"key": "MAIL_PASSWORD", "category": "mail",
     "label": "SMTP password", "value_type": "string", "secret": True},
    {"key": "MAIL_DEFAULT_SENDER", "category": "mail",
     "label": "Default sender address", "value_type": "string"},
    # --- ログ ---
    {"key": "LOG_LEVEL", "category": "logging",
     "label": "Log level", "value_type": "string"},
    {"key": "LOG_TO_DATABASE", "category": "logging",
     "label": "Write logs to database", "value_type": "boolean"},
]

__all__ = ["SYSTEM_SETTING_DEFINITIONS"]
