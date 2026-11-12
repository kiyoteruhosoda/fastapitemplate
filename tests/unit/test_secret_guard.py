"""Production does not start with the default signing key (ADR-0073 §4).

The default value is in the public repository. Access-token verification does not query the DB
(ADR-0076 §5), so a token made with that key passes with whatever permissions it claims.
"""

from __future__ import annotations

import pytest

from shared.kernel.settings.secret_guard import (
    MIN_SECRET_LENGTH,
    PRODUCTION,
    InsecureSecretError,
    require_usable_secret,
    secret_problem,
)
from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

_DEFAULT = str(DEFAULT_APPLICATION_SETTINGS["JWT_SECRET_KEY"])
_STRONG = "x" * MIN_SECRET_LENGTH


@pytest.mark.parametrize(
    ("secret", "problem"),
    [("", "empty"), (_DEFAULT, "default"), ("x" * (MIN_SECRET_LENGTH - 1), "too_short"), (_STRONG, None)],
)
def test_secret_problem_classifies_the_key(secret: str, problem: str | None) -> None:
    assert secret_problem(secret) == problem


@pytest.mark.parametrize("secret", ["", _DEFAULT, "short"])
def test_production_refuses_to_start_with_an_unusable_key(secret: str) -> None:
    with pytest.raises(InsecureSecretError):
        require_usable_secret(secret, PRODUCTION)


def test_production_starts_with_a_usable_key() -> None:
    require_usable_secret(_STRONG, PRODUCTION)


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_other_environments_only_warn(environment: str, caplog: pytest.LogCaptureFixture) -> None:
    require_usable_secret(_DEFAULT, environment)
    assert "not fit for production" in caplog.text


def test_the_app_factory_refuses_the_default_key_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shipping to production without the key means the app is not assembled (= does not start)."""
    from presentation.fastapi.app import create_app
    from shared.kernel.settings.settings import settings

    monkeypatch.setenv("APP_ENV", PRODUCTION)
    assert secret_problem(settings.jwt_secret_key) is not None, "Fix this test if the test key stops being the default"
    with pytest.raises(InsecureSecretError):
        create_app()
