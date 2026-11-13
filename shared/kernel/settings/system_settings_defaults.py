"""Default values of system settings (precedence: environment variables > DB > here).

When adding a key, also update the ``@property`` in ``settings.py`` and
``presentation/fastapi/admin/system_settings_definitions.py``
(see "Settings" in CLAUDE.md).
"""

from __future__ import annotations

DEFAULT_REFRESH_TOKEN_EXPIRES_SECONDS = 14 * 24 * 3600
#: Longer lifetimes are rejected. A wrong order of magnitude overflows the date arithmetic and every
#: sign-in fails with 500 (ADR-0101 decision 6)
MAX_REFRESH_TOKEN_EXPIRES_SECONDS = 10 * 365 * 24 * 3600

DEFAULT_APPLICATION_SETTINGS: dict[str, object] = {
    # --- Authentication ---
    # ⚠ **Production (APP_ENV=production) refuses to start with this value** (ADR-0073 §4).
    "JWT_SECRET_KEY": "default-jwt-secret-change-me-in-production",
    "ACCESS_TOKEN_ISSUER": "fastapitemplate",
    "ACCESS_TOKEN_AUDIENCE": "fastapitemplate",
    "ACCESS_TOKEN_EXPIRES_SECONDS": 300,
    "REFRESH_TOKEN_EXPIRES_SECONDS": DEFAULT_REFRESH_TOKEN_EXPIRES_SECONDS,
    # Whether each refresh restarts the lifetime from now. If false, count from sign-in (ADR-0101)
    "REFRESH_TOKEN_SLIDING_ENABLED": True,
    "SESSION_COOKIE_SECURE": False,
    "PASSWORD_RESET_TOKEN_TTL_SECONDS": 3600,
    # Adding/removing passkeys and changing email are allowed only within this many seconds of
    # sign-in (ADR-0076 §10)
    "RECENT_SIGN_IN_SECONDS": 600,
    # Failure limit per account name (ADR-0076 §9). After that many failures within the window,
    # refuse for a while
    "LOGIN_MAX_FAILURES": 5,
    "LOGIN_FAILURE_WINDOW_SECONDS": 900,
    "LOGIN_LOCK_SECONDS": 900,
    # --- Two-factor authentication (TOTP) ---
    "TOTP_ISSUER": "fastapitemplate",  # Issuer name shown in authenticator apps
    "TOTP_VALID_WINDOW": 1,  # How many time steps before/after to accept (absorbs clock drift)
    # --- Passkeys (WebAuthn) ---
    # The RP ID is what registered passkeys are bound to. Changing it invalidates existing passkeys.
    # It must be a **domain name only** (no IP address), so during development open the app at
    # localhost rather than 127.0.0.1 (mapping in docs/OPERATIONS.md).
    "WEBAUTHN_RP_ID": "localhost",
    "WEBAUTHN_RP_NAME": "fastapitemplate",
    "WEBAUTHN_ORIGIN": "http://localhost:5173",
    "WEBAUTHN_CHALLENGE_TTL_SECONDS": 300,
    # --- General ---
    "APP_BASE_URL": "",  # Base for generated links such as password reset (e.g. https://app.example.com)
    "LANGUAGES": ["en", "ja"],
    "DEFAULT_LOCALE": "en",
    "DEFAULT_THEME": "system",  # system / light / dark
    "CORS_ALLOWED_ORIGINS": [],
    # Number of **trusted** reverse proxy hops in front. X-Forwarded-For is a header the sender
    # can set freely, so by default (0) it is not trusted at all and the TCP peer address is
    # used. The bundled nginx setup uses 1 (set in docker-compose).
    "TRUSTED_PROXY_HOPS": 0,
    # --- Mail ---
    "MAIL_ENABLED": False,
    "MAIL_SERVER": "smtp.example.com",
    "MAIL_PORT": 587,
    "MAIL_USE_TLS": True,
    "MAIL_USE_SSL": False,
    "MAIL_USERNAME": "",
    "MAIL_PASSWORD": "",
    "MAIL_DEFAULT_SENDER": "",
    # --- Logging ---
    "LOG_LEVEL": "INFO",
    "LOG_TO_DATABASE": True,
    # Minimum level of records written to the DB (stdout still emits everything at LOG_LEVEL).
    # If log volume becomes a problem, raise this to WARNING to curb only the DB growth.
    "LOG_DB_MIN_LEVEL": "INFO",
    # Retention period (days). 0 means "never delete". By default neither is deleted: retention
    # is decided by operational and audit requirements, and the template should not start
    # deleting on its own. Periodic cleanup starts once a number of days is set (ADR-0075 §3).
    "LOG_RETENTION_DAYS": 0,
    # Audit logs are kept separately from application logs (small, long-lived, no rows to thin out).
    "AUDIT_LOG_RETENTION_DAYS": 0,
    # --- Notifications (ADR-0081 §3) ---
    # Location of the file holding the VAPID private key (PEM) for Web Push (device notifications).
    # When empty, device notifications cannot be sent (the bell and on-screen notices still
    # work). ⚠ Held by location, not by value.
    # See docs/OPERATIONS.md for how to create it. The public key is derived from the private
    # key, so no setting is needed.
    "WEB_PUSH_VAPID_PRIVATE_KEY_FILE": "",
    # Contact the app identifies itself with to push services (FCM / Mozilla etc.). ``mailto:`` or
    # ``https:``. The push service contacts this address if we send too much.
    "WEB_PUSH_SUBJECT": "",
    # Notifications to the mobile apps (FCM; ADR-0081 §5). Location of the Firebase service account
    # key file (JSON). When empty, nothing is sent to FCM. ⚠ Held by location, not by value.
    "FCM_SERVICE_ACCOUNT_FILE": "",
    # --- Latest mobile app release (ADR-0081 §4) ---
    # If any of the read settings (ENDPOINT_URL / OBJECT_KEY / ACCESS_KEY_ID /
    # SECRET_ACCESS_KEY_FILE) is empty, nothing is announced. ⚠ The secret key is held as a file
    # path, not a value.
    # ⚠ Give the key read access to artifacts only (with write access, the distributed APK could
    # be swapped).
    "APP_RELEASE_S3_ENDPOINT_URL": "",
    "APP_RELEASE_S3_REGION": "garage",
    "APP_RELEASE_S3_BUCKET": "artifacts",
    "APP_RELEASE_S3_OBJECT_KEY": "",  # e.g. <app name>/latest.json
    "APP_RELEASE_S3_ACCESS_KEY_ID": "",
    "APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE": "",
    # Where the browser goes when the notice is tapped (the page where people fetch the APK).
    "APP_RELEASE_DOWNLOAD_URL": "",
    # --- SSO with an external IdP (ADR-0077 §1 / ADR-0076 §3) ---
    # ⚠ **Off by default.** The template does not know the IdP. Enabling it with empty settings
    #   leaves the app starting fine but with sign-in failing.
    "OIDC_ENABLED": False,
    "OIDC_DISPLAY_NAME": "SSO",  # Name shown on the sign-in screen button
    # Issuer URL of the OpenID Provider. The URL with /.well-known/openid-configuration
    # appended must be readable (each endpoint is looked up via discovery).
    "OIDC_ISSUER": "",
    "OIDC_CLIENT_ID": "",
    "OIDC_CLIENT_SECRET": "",
    # Client authentication method for the token endpoint (ADR-0077 §1 decision 5).
    # client_secret_basic = use CLIENT_SECRET above.
    # private_key_jwt     = sign with the private key in PRIVATE_KEY_FILE below (keeps the
    #                       secret out of both deploy variables and the DB).
    # ⚠ Unknown values do not fall back to the default; they are treated as invalid (SSO is off).
    "OIDC_CLIENT_AUTH_METHOD": "client_secret_basic",
    # Used only with private_key_jwt. Pass the PEM on the host read-only.
    "OIDC_PRIVATE_KEY_FILE": "",
    # When several keys are registered at the IdP, tells which one to verify with (an RFC 7638
    # thumbprint). Can be empty if there is only one.
    "OIDC_PRIVATE_KEY_KID": "",
    # client_id used when this app calls the IdP **as a machine** (ADR-0077 §7). Registered in
    # assay as a service account; a separate registration from the sign-in OIDC_CLIENT_ID.
    # Shares the key OIDC_PRIVATE_KEY_FILE / KID above; the method is always private_key_jwt.
    # When empty, periodic reconciliation does not run. ⚠ Until assay binds it to the app's
    # identity, calls are skipped with 403.
    "MACHINE_CLIENT_ID": "",
    "OIDC_SCOPES": ["openid", "profile", "email"],
    # Redirect URI registered at the IdP. When empty, APP_BASE_URL + /api/auth/sso/callback.
    "OIDC_REDIRECT_URI": "",
    # Whether sign-out is passed through to the IdP (RP-Initiated Logout 1.0). **Off by default.**
    # ⚠ **Turning it on affects other apps.** What ends is the IdP's SSO session, so signing out
    #   of this app also affects other apps' "next SSO sign-in".
    #   Apps with local accounts can leave it off (/logout already ends their own session).
    #   Details in the settings.oidc_rp_logout_enabled docstring.
    "OIDC_RP_LOGOUT_ENABLED": False,
    # Where the IdP returns after sign-out. When empty, APP_BASE_URL + /api/auth/sso/signed-out.
    # ⚠ **Only used if it exactly matches the IdP-side registration** (if unregistered, it does
    #   not fail but stops at the IdP's own completion page).
    "OIDC_POST_LOGOUT_REDIRECT_URI": "",
    # Requested authentication strength (``acr_values``). Empty = none (ADR-0076 §3 decision 1).
    # ⚠ **Setting it makes sign-in fail closed.** If the returned acr does not match the request
    #   (or none is returned), sign-in is refused. Leave it empty when connecting to an IdP
    #   without reserved values. With our own idp (assay), urn:assay:ac:mfa is available.
    "OIDC_ACR_VALUES": [],
    # Claim name mapping (differs per IdP)
    "OIDC_EMAIL_CLAIM": "email",
    "OIDC_USERNAME_CLAIM": "name",
    # IdP group -> this app's role. A list of "<group>=<role>".
    # Role given to users who match no mapping
    "OIDC_DEFAULT_ROLES": [],
    # Re-derive roles from IdP groups on every sign-in (the IdP is the source of truth).
    # Default false = only granted at first provisioning (so roles added on the admin screen
    # are not stripped on each sign-in).
    "OIDC_ROLE_SYNC": False,
    # ⚠ **Whether unknown users are created on first sign-in. Default false.** If the IdP is
    #   shared across tenants, true means "everyone with an IdP account can enter this app".
    "OIDC_AUTO_PROVISION": False,
    # ⚠ **Whether first sign-in links to an existing local account. Default false** (ADR-0077 §4).
    #   With our own idp (assay), the email_verified condition means "the tenant administrator
    #   claims so", not proof by the person. If you enable it, check how the connected IdP sets
    #   this value.
    "OIDC_LINK_BY_EMAIL": False,
    # Accepted email domains (empty = no restriction)
    "OIDC_ALLOWED_EMAIL_DOMAINS": [],
    # Time allowed for the authorization request -> callback round trip (lifetime of the signed cookie)
    "OIDC_LOGIN_TRANSACTION_TTL_SECONDS": 600,
    # Lifetime of the exchange ticket issued by the callback (the SPA exchanges it for tokens)
    "OIDC_LOGIN_TICKET_TTL_SECONDS": 60,
    # --- Local sign-in (ADR-0076 §3 decisions 2 and 3) ---
    # ⚠ **false blocks sign-in with password and passkey.** Registering local credentials
    #   (passkey, TOTP, password change) stops too (so no spare key to a closed door can be
    #   made). If locked out, set the environment variable back to true and restart.
    "LOCAL_LOGIN_ENABLED": True,
    # Require two-factor authentication for password sign-in (ADR-0093). One switch for the app.
    # ⚠ To revert, use the screen or scripts/unset_setting.py (saved values beat env vars).
    "LOCAL_TWO_FACTOR_REQUIRED": False,
}

#: Settings decided by environment variables only (ADR-0090): where the server connects to, and
#: locations of key files. Shown read-only on the admin screen; saving is refused. Stale values
#: left in the DB are not read.
ENV_ONLY_SETTINGS: frozenset[str] = frozenset(
    {
        "OIDC_ISSUER",
        "OIDC_PRIVATE_KEY_FILE",
        "WEB_PUSH_VAPID_PRIVATE_KEY_FILE",
        "FCM_SERVICE_ACCOUNT_FILE",
        "APP_RELEASE_S3_ENDPOINT_URL",
        "APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE",
    }
)

__all__ = ["DEFAULT_APPLICATION_SETTINGS", "ENV_ONLY_SETTINGS"]
