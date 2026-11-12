"""Settings resolution precedence (DB > environment variable > default).

The DB layer (system_settings overrides) is tested on the integration side.
"""

from shared.kernel.settings.settings import ApplicationSettings
from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS


def test_default_value_used_when_env_missing() -> None:
    s = ApplicationSettings(env={})
    assert s.access_token_issuer == "fastapitemplate"
    assert s.mail_enabled is False


def test_env_overrides_default() -> None:
    s = ApplicationSettings(env={"ACCESS_TOKEN_ISSUER": "custom", "MAIL_ENABLED": "true"})
    assert s.access_token_issuer == "custom"
    assert s.mail_enabled is True


def test_blank_env_value_is_ignored() -> None:
    s = ApplicationSettings(env={"ACCESS_TOKEN_ISSUER": ""})
    assert s.access_token_issuer == "fastapitemplate"


def test_int_parsing_with_invalid_value_falls_back() -> None:
    s = ApplicationSettings(env={"ACCESS_TOKEN_EXPIRES_SECONDS": "not-a-number"})
    assert s.access_token_expires_seconds == 900


def test_list_parsing_from_json_and_csv() -> None:
    assert ApplicationSettings(env={"CORS_ALLOWED_ORIGINS": '["http://a", "http://b"]'}).cors_allowed_origins == [
        "http://a",
        "http://b",
    ]
    assert ApplicationSettings(env={"CORS_ALLOWED_ORIGINS": "http://a, http://b"}).cors_allowed_origins == [
        "http://a",
        "http://b",
    ]


def test_database_uri_is_env_only() -> None:
    s = ApplicationSettings(env={"DATABASE_URI": "sqlite:///x.db"})
    assert s.database_uri == "sqlite:///x.db"


def test_the_unused_secret_key_setting_is_gone() -> None:
    """Signing uses only JWT_SECRET_KEY. Holding unread secrets leads to rotating the wrong key."""
    assert "SECRET_KEY" not in DEFAULT_APPLICATION_SETTINGS
    assert not hasattr(ApplicationSettings, "secret_key")


def test_a_leftover_secret_key_in_the_environment_is_ignored() -> None:
    """Does not block startup even if it remains in a derived app's declaration."""
    assert ApplicationSettings(env={"SECRET_KEY": "left-over"}).access_token_issuer == "fastapitemplate"
