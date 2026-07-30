"""設定解決の優先順位（環境変数 > デフォルト値）の検証。

DB 層（system_settings 上書き）は integration 側で検証する。
"""

from shared.kernel.settings.settings import ApplicationSettings


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
