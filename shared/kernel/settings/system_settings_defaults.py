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
    # --- 外部 IdP との SSO（ADR-0025 / ADR-0026） ---
    # ⚠ **既定は無効。** テンプレートは連携先を知らない。設定が空のまま有効にすると、
    #   起動はするのにログインだけが失敗する状態になる。
    "OIDC_ENABLED": False,
    "OIDC_DISPLAY_NAME": "SSO",  # ログイン画面のボタンに出る名前
    # OpenID Provider の発行者 URL。末尾に /.well-known/openid-configuration を
    # 付けた先が読める必要がある（discovery で各エンドポイントを引く）。
    "OIDC_ISSUER": "",
    "OIDC_CLIENT_ID": "",
    "OIDC_CLIENT_SECRET": "",
    # トークンエンドポイントへの client 認証方式（ADR-0025 決定 5）。
    # client_secret_basic = 上の CLIENT_SECRET を使う。
    # private_key_jwt     = 下の PRIVATE_KEY_FILE の秘密鍵で署名する（秘密を
    #                       デプロイの変数にも DB にも置かずに済む）。
    # ⚠ 知らない値は既定へ落とさず「不備」として扱う（SSO が無効になる）。
    "OIDC_CLIENT_AUTH_METHOD": "client_secret_basic",
    # private_key_jwt のときだけ使う。ホスト上の PEM を read-only で渡す。
    "OIDC_PRIVATE_KEY_FILE": "",
    # IdP に鍵が複数登録されているときに、どれで検証するかを示す（RFC 7638 の
    # サムプリント）。1 つしか無ければ空でよい。
    "OIDC_PRIVATE_KEY_KID": "",
    "OIDC_SCOPES": ["openid", "profile", "email"],
    # IdP に登録するリダイレクト URI。空なら APP_BASE_URL + /api/auth/sso/callback。
    "OIDC_REDIRECT_URI": "",
    # 要求する認証の強度（``acr_values``）。空 = 要求しない（ADR-0026 決定 1）。
    # ⚠ **入れたら fail closed になる。** 返ってきた acr が要求と一致しなければ
    #   （返ってこない場合も）ログインを断る。予約語を持たない IdP へつなぐときは
    #   空のままにする。自前 idp（assay）なら urn:assay:ac:mfa が使える。
    "OIDC_ACR_VALUES": [],
    # クレーム名の対応付け（IdP ごとに異なる）
    "OIDC_EMAIL_CLAIM": "email",
    "OIDC_USERNAME_CLAIM": "name",
    "OIDC_GROUPS_CLAIM": "groups",
    # IdP のグループ -> このアプリのロール。"<グループ>=<ロール>" の並び。
    "OIDC_ROLE_MAPPING": [],
    # 対応付けに当たらなかった利用者へ与えるロール
    "OIDC_DEFAULT_ROLES": [],
    # 毎回のログインでロールを IdP のグループから引き直す（IdP を正とする）。
    # 既定は false = 初回のプロビジョニング時にだけ与える（管理画面で足したロールが
    # ログインのたびに剥がれるのを避ける）。
    "OIDC_ROLE_SYNC": False,
    # ⚠ **未知の利用者を初回ログインで作るか。既定は false。** IdP がテナント共用の
    #   場合、true は「IdP に口座がある人は全員このアプリに入れる」を意味する。
    "OIDC_AUTO_PROVISION": False,
    # 既存のローカルアカウントと**検証済みの**メールアドレスで結び付ける
    "OIDC_LINK_BY_EMAIL": True,
    # 受け入れるメールアドレスのドメイン（空 = 制限しない）
    "OIDC_ALLOWED_EMAIL_DOMAINS": [],
    # 認可要求 -> コールバックの往復に許す時間（署名付き Cookie の寿命）
    "OIDC_LOGIN_TRANSACTION_TTL_SECONDS": 600,
    # コールバックが発行する引き換え券（SPA がトークンへ交換する）の寿命
    "OIDC_LOGIN_TICKET_TTL_SECONDS": 60,
    # --- ローカルの入口（ADR-0026 決定 2・3） ---
    # ⚠ **false にするとパスワード・パスキーでのログインが塞がる。** 併せてローカルの
    #   資格情報の登録（パスキー・TOTP・パスワード変更）も止まる（閉じた入口の合鍵を
    #   作れないようにするため）。締め出されたら環境変数で true へ戻して再起動する。
    "LOCAL_LOGIN_ENABLED": True,
}

__all__ = ["DEFAULT_APPLICATION_SETTINGS"]
