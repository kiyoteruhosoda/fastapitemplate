"""システム設定のデフォルト値（優先順位: 環境変数 > DB > ここ）。

キーを追加したら ``settings.py`` の ``@property`` と
``presentation/fastapi/admin/system_settings_definitions.py`` も更新する
（CLAUDE.md「設定管理」参照）。
"""

from __future__ import annotations

DEFAULT_APPLICATION_SETTINGS: dict[str, object] = {
    # --- 認証 ---
    "SECRET_KEY": "default-secret-key",
    "JWT_SECRET_KEY": "default-jwt-secret-change-me-in-production",
    "ACCESS_TOKEN_ISSUER": "fastapitemplate",
    "ACCESS_TOKEN_AUDIENCE": "fastapitemplate",
    "ACCESS_TOKEN_EXPIRES_SECONDS": 900,
    "REFRESH_TOKEN_EXPIRES_SECONDS": 14 * 24 * 3600,
    "SESSION_COOKIE_SECURE": False,
    "PASSWORD_RESET_TOKEN_TTL_SECONDS": 3600,
    # --- 二要素認証（TOTP） ---
    "TOTP_ISSUER": "fastapitemplate",  # 認証アプリに表示される発行者名
    "TOTP_VALID_WINDOW": 1,  # 前後いくつの時間枠を許容するか（時刻ずれ吸収）
    # --- パスキー（WebAuthn） ---
    # RP ID は登録済みパスキーの結び付け先。変更すると既存のパスキーが無効になる。
    # 指定できるのは**ドメイン名のみ**（IP アドレス不可）。そのため開発時は
    # 127.0.0.1 ではなく localhost で開く（docs/OPERATIONS.md に対応表）。
    "WEBAUTHN_RP_ID": "localhost",
    "WEBAUTHN_RP_NAME": "fastapitemplate",
    "WEBAUTHN_ORIGIN": "http://localhost:5173",
    "WEBAUTHN_CHALLENGE_TTL_SECONDS": 300,
    # --- 一般 ---
    "APP_BASE_URL": "",  # パスワードリセットリンク等の生成元（例: https://app.example.com）
    "LANGUAGES": ["en", "ja"],
    "DEFAULT_LOCALE": "en",
    "DEFAULT_THEME": "system",  # system / light / dark
    "CORS_ALLOWED_ORIGINS": [],
    # 前段に置いた**信頼できる**リバースプロキシの段数。X-Forwarded-For は
    # 送信元が自由に付けられるヘッダーなので、既定（0）では一切信用せず TCP の
    # 接続元を使う。同梱の nginx 構成では 1（docker-compose で設定済み）。
    "TRUSTED_PROXY_HOPS": 0,
    # --- メール ---
    "MAIL_ENABLED": False,
    "MAIL_SERVER": "smtp.example.com",
    "MAIL_PORT": 587,
    "MAIL_USE_TLS": True,
    "MAIL_USE_SSL": False,
    "MAIL_USERNAME": "",
    "MAIL_PASSWORD": "",
    "MAIL_DEFAULT_SENDER": "",
    # --- ログ ---
    "LOG_LEVEL": "INFO",
    "LOG_TO_DATABASE": True,
    # DB へ書くレコードの下限レベル（stdout は LOG_LEVEL のまま全量出す）。
    # ログ量が問題になったら WARNING へ上げて DB の増え方だけを抑える。
    "LOG_DB_MIN_LEVEL": "INFO",
    # 保持期間（日）。0 は「削除しない」。既定ではどちらも消さない——保持期間は
    # 運用・監査の要件で決まるもので、テンプレートが勝手に消し始めてよいものでは
    # ないため。日数を入れた時点で定期的な掃除が働く（ADR-0021）。
    "LOG_RETENTION_DAYS": 0,
    # 監査ログはアプリログと分けて持つ（少量・長命で、間引いてよい行が無い）。
    "AUDIT_LOG_RETENTION_DAYS": 0,
}

__all__ = ["DEFAULT_APPLICATION_SETTINGS"]
