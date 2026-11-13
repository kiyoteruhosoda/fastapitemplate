"""Single point of access to application settings.

Always read setting values through the ``@property`` accessors of this module's
:data:`settings` (:class:`ApplicationSettings`). Do not call ``os.getenv`` or read the DB directly
(see "Settings" in CLAUDE.md).

Precedence: **environment variables > DB (system_settings table) > default values**.

Tests can build their own ``ApplicationSettings(env=...)`` to verify behaviour.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_REFRESH_TOKEN_EXPIRES_SECONDS,
    ENV_ONLY_SETTINGS,
    MAX_REFRESH_TOKEN_EXPIRES_SECONDS,
)

_logger = logging.getLogger(__name__)


class _DatabaseOverrides:
    """The DB layer of the "environment variables > DB > defaults" precedence.

    Supplies the ``app.config`` record of the ``system_settings`` table that the admin
    screen saves.

    - When the DB is not reachable or the table does not exist yet (before migrations),
      it silently returns no values and keeps running on env vars and defaults alone.
    - Keeps a TTL cache to avoid a DB access per request. When the admin screen saves,
      ``SystemSettingService`` calls ``invalidate()`` so the change applies immediately.
    - Reads through a dedicated short-lived connection (so the transaction state of
      the shared session is not disturbed).
    """

    _SETTING_KEY = "app.config"
    _TTL_SECONDS = 10.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loading = threading.local()
        self._payload: dict[str, Any] = {}
        self._unreadable = False
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._payload = {}
        self._expires_at = 0.0

    def get(self, key: str) -> Any:
        if key not in DEFAULT_APPLICATION_SETTINGS:
            # Only keys editable on the admin screen are overridden from the DB. Resolving
            # bootstrap keys such as DATABASE_URI here would recurse.
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
            self._note_readable()
        except Exception:
            # Keep the last good values and do not retry until the next TTL
            self._note_unreadable()
        finally:
            self._loading.active = False
            self._expires_at = time.monotonic() + self._TTL_SECONDS

    def _note_unreadable(self) -> None:
        """Report that settings can no longer be read from the DB.

        Swallowing it silently leaves only the symptom "a value saved on the admin screen
        has no effect", with the cause (DB not reachable, before migrations) shown nowhere.
        Logging every TTL would flood the log, so emit one line **only when the state changes**.
        """
        if self._unreadable:
            return
        self._unreadable = True
        _logger.warning("system_settings_unreadable", exc_info=True)

    def _note_readable(self) -> None:
        if not self._unreadable:
            return
        self._unreadable = False
        _logger.info("system_settings_readable")

    def _load_payload(self) -> dict[str, Any] | None:
        from shared.kernel.settings.system_setting_records import (
            SystemSettingRecordReader,
        )

        value = SystemSettingRecordReader.read_json(self._SETTING_KEY)
        if value is None:
            return {}
        return value if isinstance(value, dict) else {}


#: SSO callback path. Used to build ``OIDC_REDIRECT_URI`` when it is not set
#: (keep in sync with the router ``prefix``).
OIDC_CALLBACK_PATH = "/api/auth/sso/callback"

#: Landing path of RP-Initiated Logout. Used to build ``OIDC_POST_LOGOUT_REDIRECT_URI``
#: when it is not set (keep in sync with the router ``prefix``).
OIDC_SIGNED_OUT_PATH = "/api/auth/sso/signed-out"


class ApplicationSettings:
    """Merge DB, env vars and defaults into setting values (strongest first)."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env: Mapping[str, str] = os.environ if env is None else env
        self._db = _DatabaseOverrides()

    # ------------------------------------------------------------------
    # Resolution logic
    # ------------------------------------------------------------------

    def _get(self, key: str, default: Any = None) -> Any:
        """⚠ **The DB (admin screen) beats environment variables.**

        Environment variables are "initial values at deploy time"; **the place to change a value
        during operation is the screen**. The other way round, once someone writes a line in
        compose, that key can no longer be changed from the screen: **it is shown on the screen
        but cannot be changed**.

        ⚠ **Bootstrap keys are outside this order** (`DATABASE_URI` etc.). Reading a key from
        the DB that is needed to connect to the DB would recurse, so the section below reads
        `self._env` directly.

        ⚠ **Outbound destinations and key locations (`ENV_ONLY_SETTINGS`) are also outside the
        order** (ADR-0090). A value left in the DB is not read.
        """
        if key not in ENV_ONLY_SETTINGS:
            db_value = self._db.get(key)
            if db_value is not None:
                return db_value
        env_value = self._env.get(key)
        if env_value is not None and env_value != "":
            return env_value
        return DEFAULT_APPLICATION_SETTINGS.get(key, default)

    def resolve(self, key: str, default: Any = None) -> Any:
        """Resolve a key in precedence order (for showing current values on the admin screen).

        Regular code should use the typed ``@property`` accessors.
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
        except TypeError, ValueError:
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
        """Discard the DB override cache (right after saving settings, and for test cleanup)."""
        self._db.invalidate()

    # ------------------------------------------------------------------
    # Bootstrap (environment variables only; never overridden from the DB)
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

    @property
    def app_client_ids(self) -> frozenset[str]:
        """``client_id`` of the clients (apps) whose assay access tokens may be accepted (ADR-0081 §1).

        ⚠ **Environment variable only.** If it could be added from the screen, tokens issued for
        another client would pass this app's API. When empty, no assay token is accepted at all.
        """
        return frozenset(_env_list(self._env.get("APP_CLIENT_IDS")))

    @property
    def machine_clients(self) -> list[object]:
        """Allow list of the machine endpoints (a JSON array; ADR-0087). Each entry is
        ``{"client_id", "name", "acts_as", "operations": ["<permission code>", ...]}``.

        ⚠ **Environment variable only.** If it could be added from the screen, anyone who can
        write settings could make a machine do anything.
        ⚠ **Empty unless it is a JSON array** (a misspelled setting must not let anyone in).
        When empty, the machine endpoints are closed.
        """
        raw = self._env.get("MACHINE_CLIENTS")
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except ValueError:
            _logger.warning("machine_clients_unreadable")
            return []
        return list(parsed) if isinstance(parsed, list) else []

    @property
    def machine_audience(self) -> str:
        """Audience (``aud``) of tokens accepted by the machine endpoints: the name of the
        ``resources`` registered in assay (ADR-0082 §2 decision 4).

        ⚠ **Environment variable only. When empty, the machine endpoints are closed** (without
        checking the audience, tokens meant for another app would pass).
        """
        return (self._env.get("MACHINE_AUDIENCE") or "").strip()

    @property
    def android_app_package(self) -> str:
        """Package name of the Android app that App Links return to (``assetlinks.json``; ADR-0081 §1)."""
        return (self._env.get("ANDROID_APP_PACKAGE") or "").strip()

    @property
    def android_app_cert_fingerprints(self) -> tuple[str, ...]:
        """SHA-256 fingerprints of that app's signing certificate (``AA:BB:…`` format)."""
        return tuple(_env_list(self._env.get("ANDROID_APP_CERT_FINGERPRINTS")))

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

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
        """⚠ Unusable values (0 or less, too long) fall back to the default. Env vars skip the
        validation done on save (ADR-0101)."""
        value = self.get_int("REFRESH_TOKEN_EXPIRES_SECONDS", DEFAULT_REFRESH_TOKEN_EXPIRES_SECONDS)
        return value if 0 < value <= MAX_REFRESH_TOKEN_EXPIRES_SECONDS else DEFAULT_REFRESH_TOKEN_EXPIRES_SECONDS

    @property
    def refresh_token_sliding_enabled(self) -> bool:
        """Whether each refresh restarts the lifetime from now. If false, count from sign-in (ADR-0101)."""
        return self.get_bool("REFRESH_TOKEN_SLIDING_ENABLED", True)

    @property
    def session_cookie_secure(self) -> bool:
        return self.get_bool("SESSION_COOKIE_SECURE", False)

    @property
    def password_reset_token_ttl_seconds(self) -> int:
        return self.get_int("PASSWORD_RESET_TOKEN_TTL_SECONDS", 3600)

    @property
    def recent_sign_in_seconds(self) -> int:
        """Seconds since sign-in during which operations that rebuild sign-in methods are allowed
        (ADR-0076 §10)."""
        return max(self.get_int("RECENT_SIGN_IN_SECONDS", 600), 1)

    @property
    def login_max_failures(self) -> int:
        """How many failures are allowed within the window. ``0`` disables counting (never 0 in
        production; ADR-0076 §9)."""
        return max(self.get_int("LOGIN_MAX_FAILURES", 5), 0)

    @property
    def login_failure_window_seconds(self) -> int:
        return max(self.get_int("LOGIN_FAILURE_WINDOW_SECONDS", 900), 1)

    @property
    def login_lock_seconds(self) -> int:
        return max(self.get_int("LOGIN_LOCK_SECONDS", 900), 1)

    # ------------------------------------------------------------------
    # Two-factor authentication (TOTP)
    # ------------------------------------------------------------------

    @property
    def totp_issuer(self) -> str:
        return str(self._get("TOTP_ISSUER"))

    @property
    def totp_valid_window(self) -> int:
        return self.get_int("TOTP_VALID_WINDOW", 1)

    # ------------------------------------------------------------------
    # Passkeys (WebAuthn)
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
    # General
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

    @property
    def trusted_proxy_hops(self) -> int:
        """Number of trusted reverse proxy hops (0 = do not trust ``X-Forwarded-For``)."""
        return max(self.get_int("TRUSTED_PROXY_HOPS", 0), 0)

    # ------------------------------------------------------------------
    # Mail
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
    # Logging
    # ------------------------------------------------------------------

    @property
    def log_level(self) -> str:
        return str(self._get("LOG_LEVEL"))

    @property
    def log_to_database(self) -> bool:
        return self.get_bool("LOG_TO_DATABASE", True)

    @property
    def log_db_min_level(self) -> str:
        """Minimum level of records written to the DB (``log`` table)."""
        return str(self._get("LOG_DB_MIN_LEVEL"))

    @property
    def log_retention_days(self) -> int:
        """Days to keep ``log``. ``0`` never deletes (ADR-0075 §3)."""
        return self.get_int("LOG_RETENTION_DAYS", 0)

    @property
    def audit_log_retention_days(self) -> int:
        """Days to keep ``audit_log``. ``0`` never deletes (ADR-0075 §3)."""
        return self.get_int("AUDIT_LOG_RETENTION_DAYS", 0)

    # ------------------------------------------------------------------
    # Notifications (ADR-0081 §3)
    # ------------------------------------------------------------------

    @property
    def web_push_vapid_private_key_file(self) -> str:
        """Location of the file holding the Web Push VAPID private key (PEM). When empty, no
        device notifications are sent.

        ⚠ **Held by location, not by value.** The content is read from the file on every send,
        so it appears neither in the settings list nor in backups.
        """
        return self._text("WEB_PUSH_VAPID_PRIVATE_KEY_FILE")

    @property
    def web_push_subject(self) -> str:
        """Contact the app identifies itself with to the push service (``mailto:`` / ``https:``)."""
        return self._text("WEB_PUSH_SUBJECT")

    @property
    def fcm_service_account_file(self) -> str:
        """Location of the Firebase service account key file (JSON). When empty, nothing is sent to
        the apps (ADR-0081 §5)."""
        return self._text("FCM_SERVICE_ACCOUNT_FILE")

    # ------------------------------------------------------------------
    # Latest mobile app release (ADR-0081 §4)
    # ------------------------------------------------------------------

    @property
    def app_release_s3_endpoint_url(self) -> str:
        """URL of the mobile app distribution store (S3-compatible). When empty, no latest version
        is announced."""
        return self._text("APP_RELEASE_S3_ENDPOINT_URL")

    @property
    def app_release_s3_region(self) -> str:
        """Region of the distribution store. ``garage`` for Garage (match the store's ``s3_region``)."""
        return self._text("APP_RELEASE_S3_REGION")

    @property
    def app_release_s3_bucket(self) -> str:
        """Bucket of the distribution store (``artifacts``)."""
        return self._text("APP_RELEASE_S3_BUCKET")

    @property
    def app_release_s3_object_key(self) -> str:
        """Object the release procedure writes to point at the latest version
        (``<app name>/latest.json``)."""
        return self._text("APP_RELEASE_S3_OBJECT_KEY")

    @property
    def app_release_s3_access_key_id(self) -> str:
        """ID of the key that reads the distribution store (not secret; the secret is in the file below)."""
        return self._text("APP_RELEASE_S3_ACCESS_KEY_ID")

    @property
    def app_release_s3_secret_access_key_file(self) -> str:
        """Path of the file holding that key's secret (⚠ held by location, not by value)."""
        return self._text("APP_RELEASE_S3_SECRET_ACCESS_KEY_FILE")

    @property
    def app_release_download_url(self) -> str:
        """Where the browser goes when the latest-version notice is tapped. When empty, the notice
        has no link."""
        return self._text("APP_RELEASE_DOWNLOAD_URL")

    def _text(self, key: str) -> str:
        value = self._get(key)
        return str(value).strip() if value else ""

    # ------------------------------------------------------------------
    # SSO with an external IdP (ADR-0077 §1 / ADR-0076 §3)
    # ------------------------------------------------------------------

    @property
    def oidc_enabled(self) -> bool:
        """Whether SSO is used. **Does not check whether the configuration is complete**
        (:attr:`oidc_configured`)."""
        return self.get_bool("OIDC_ENABLED", False)

    @property
    def oidc_configured(self) -> bool:
        """Enabled and the endpoint is filled in (decides whether the sign-in screen shows the button).

        Whether the credentials are complete is checked per method by ``ClientCredential``.
        """
        return self.oidc_enabled and bool(self.oidc_issuer and self.oidc_client_id)

    @property
    def oidc_display_name(self) -> str:
        return str(self._get("OIDC_DISPLAY_NAME") or "SSO")

    @property
    def oidc_issuer(self) -> str:
        return str(self._get("OIDC_ISSUER") or "").rstrip("/")

    @property
    def oidc_client_id(self) -> str:
        return str(self._get("OIDC_CLIENT_ID") or "")

    @property
    def oidc_client_secret(self) -> str:
        return str(self._get("OIDC_CLIENT_SECRET") or "")

    @property
    def oidc_client_auth_method(self) -> str:
        """Client authentication method for the token endpoint (ADR-0077 §1 decision 5).

        Unknown values do not fall back to the default (``ClientCredential`` treats them as invalid).
        """
        return str(self._get("OIDC_CLIENT_AUTH_METHOD") or "").strip()

    @property
    def oidc_private_key_file(self) -> str:
        """Location of the private key (PEM) used to sign ``private_key_jwt``.

        ⚠ The container's runtime gid must be able to access **both the file and its directory**.
        """
        return str(self._get("OIDC_PRIVATE_KEY_FILE") or "")

    @property
    def oidc_private_key_kid(self) -> str:
        return str(self._get("OIDC_PRIVATE_KEY_KID") or "")

    @property
    def machine_client_id(self) -> str:
        """``client_id`` this app uses when acting **as a machine** (ADR-0077 §7).

        ⚠ A **separate registration** from the one for user sign-in (``OIDC_CLIENT_ID``); only the
        key is shared.
        ⚠ **Do not name it after a purpose** (not ``RECONCILE_…``). Which app it belongs to is
        assay's decision; this side does not declare different identities per purpose.
        """
        return str(self._get("MACHINE_CLIENT_ID") or "")

    @property
    def oidc_scopes(self) -> Sequence[str]:
        return self.get_list("OIDC_SCOPES")

    @property
    def oidc_redirect_uri(self) -> str:
        """Redirect URI registered at the IdP. When empty, built from ``APP_BASE_URL``."""
        configured = str(self._get("OIDC_REDIRECT_URI") or "")
        if configured:
            return configured
        base = self.app_base_url.rstrip("/")
        return f"{base}{OIDC_CALLBACK_PATH}" if base else ""

    @property
    def oidc_rp_logout_enabled(self) -> bool:
        """Whether sign-out is passed through to the IdP (RP-Initiated Logout 1.0). **Off by default.**

        **Turning it on has side effects.** What ends is the IdP's SSO session, so signing out of
        this app also affects **the next SSO sign-in of other apps** (they will need to sign in
        again). Existing sessions of other apps are not ended: those are each app's own cookies,
        and the IdP only notifies clients that registered a ``backchannel_logout_uri``.

        **Apps with local accounts can leave it off.** ``/logout`` already ends this app's own
        session, and there is no reason to add side effects on other apps. It is worth turning on
        for **apps that can only be entered via SSO** (the IdP session is the only session) and
        **control panels opened on shared devices** (where re-entering with one button after
        sign-out would be a problem).

        If all you want is "make users sign in again every time for this app only", the
        authorization request's ``prompt=login`` has no side effects and is the better choice.
        """
        return self.get_bool("OIDC_RP_LOGOUT_ENABLED", False)

    @property
    def oidc_post_logout_redirect_uri(self) -> str:
        """Where the IdP returns after sign-out. When empty, built from ``APP_BASE_URL``.

        ⚠ **Only used if it exactly matches the IdP-side registration.** If unregistered, it does
        not fail but stops at the IdP's own completion page (the sign-out itself still works).
        """
        configured = str(self._get("OIDC_POST_LOGOUT_REDIRECT_URI") or "")
        if configured:
            return configured
        base = self.app_base_url.rstrip("/")
        return f"{base}{OIDC_SIGNED_OUT_PATH}" if base else ""

    @property
    def oidc_acr_values(self) -> Sequence[str]:
        """Requested authentication strength. Empty = none requested (ADR-0076 §3 decision 1)."""
        return self.get_list("OIDC_ACR_VALUES")

    @property
    def oidc_email_claim(self) -> str:
        return str(self._get("OIDC_EMAIL_CLAIM") or "email")

    @property
    def oidc_username_claim(self) -> str:
        return str(self._get("OIDC_USERNAME_CLAIM") or "name")

    @property
    def oidc_default_roles(self) -> Sequence[str]:
        return self.get_list("OIDC_DEFAULT_ROLES")

    @property
    def oidc_role_sync(self) -> bool:
        return self.get_bool("OIDC_ROLE_SYNC", False)

    @property
    def oidc_auto_provision(self) -> bool:
        return self.get_bool("OIDC_AUTO_PROVISION", False)

    @property
    def oidc_link_by_email(self) -> bool:
        """On first sign-in, whether to link to an existing user with the same email (ADR-0077 §4).

        ⚠ **Not linked by default.** If the meaning of ``email_verified`` differs on the IdP side,
        merely claiming someone's address becomes a way into their account.
        """
        return self.get_bool("OIDC_LINK_BY_EMAIL", False)

    @property
    def oidc_allowed_email_domains(self) -> Sequence[str]:
        return self.get_list("OIDC_ALLOWED_EMAIL_DOMAINS")

    @property
    def oidc_login_transaction_ttl_seconds(self) -> int:
        """Time allowed from the authorization request to the callback (lifetime of the signed cookie)."""
        return self.get_int("OIDC_LOGIN_TRANSACTION_TTL_SECONDS", 600)

    @property
    def oidc_login_ticket_ttl_seconds(self) -> int:
        return self.get_int("OIDC_LOGIN_TICKET_TTL_SECONDS", 60)

    # ------------------------------------------------------------------
    # Local sign-in (ADR-0076 §3 decisions 2 and 3)
    # ------------------------------------------------------------------

    @property
    def local_login_enabled(self) -> bool:
        """Whether sign-in with password or passkey and registering local credentials are allowed.

        ⚠ **There is a lockout path.** With ``false``, if the IdP goes down or the last
        administrator is suspended at the IdP, nobody can get in. To recover, set the environment
        variable back to ``true`` and restart (env vars take precedence over the DB setting).
        """
        return self.get_bool("LOCAL_LOGIN_ENABLED", True)

    @property
    def local_two_factor_required(self) -> bool:
        """Whether two-factor authentication is required for password sign-in (ADR-0093).

        Has no effect while local sign-in is closed. When closed, registration is refused too, so
        enforcing it would be a dead end.
        """
        return self.local_login_enabled and self.get_bool("LOCAL_TWO_FACTOR_REQUIRED", False)


def _env_list(raw: str | None) -> list[str]:
    """List from an environment variable (a JSON array or comma-separated). Empty items are dropped."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = raw.split(",")
    items = parsed if isinstance(parsed, list) else [parsed]
    return [str(item).strip() for item in items if str(item).strip()]


settings = ApplicationSettings()

__all__ = ["OIDC_CALLBACK_PATH", "OIDC_SIGNED_OUT_PATH", "ApplicationSettings", "settings"]
