"""本番では既定の署名鍵で起動しない（ADR-0056）。

既定値は公開リポジトリに載っている。アクセストークンの検証は DB を引かない
（ADR-0041）ので、その鍵で作ったトークンは書いた権限のまま通る。
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
    """鍵を渡し忘れて本番に出すと、アプリが組み上がらない（＝起動しない）。"""
    from presentation.fastapi.app import create_app
    from shared.kernel.settings.settings import settings

    monkeypatch.setenv("APP_ENV", PRODUCTION)
    assert secret_problem(settings.jwt_secret_key) is not None, "試験の鍵が既定値でなくなったら、この試験を直す"
    with pytest.raises(InsecureSecretError):
        create_app()
