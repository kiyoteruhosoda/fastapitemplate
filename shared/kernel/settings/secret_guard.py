"""起動時に署名鍵を確かめる（ADR-0056）。

**本番（``APP_ENV=production``）では既定の鍵で起動しない。** 既定値は公開
リポジトリに載っているので、それで発行したトークンは誰でも偽造できる。しかも
アクセストークンの検証は DB を引かない（ADR-0041）ので、偽造したトークンが
書いた権限のまま通る。警告はログにしか出ず、本番のログを毎日読む人はいない。
気付かせる唯一確実な方法は動かないことである。

それ以外の環境では警告だけ出して起動する。開発で偽造できる鍵に困る人はいない。

鍵の値そのものはログに出さない。出すのは分類（空・既定のまま・短すぎる）だけ。
"""

from __future__ import annotations

import logging

from shared.kernel.settings.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

logger = logging.getLogger(__name__)

#: 既定値では動かさない環境名（``APP_ENV``）
PRODUCTION = "production"
#: 256 ビットを base64 にした長さに相当。``openssl rand -base64 48`` で 64 文字になる
MIN_SECRET_LENGTH = 32


class InsecureSecretError(RuntimeError):
    """本番で使えない署名鍵。起動を止めるために投げる。"""


def secret_problem(secret: str) -> str | None:
    """鍵の何が駄目かの分類。問題が無ければ ``None``。

    「既定値ではない」は「強い」を意味しない。長さも見る。
    """
    if not secret:
        return "empty"
    if secret == DEFAULT_APPLICATION_SETTINGS["JWT_SECRET_KEY"]:
        return "default"
    if len(secret) < MIN_SECRET_LENGTH:
        return "too_short"
    return None


def require_usable_secret(secret: str, environment: str) -> None:
    """本番なら駄目な鍵で落とし、それ以外なら警告する。"""
    problem = secret_problem(secret)
    if problem is None:
        return
    if environment == PRODUCTION:
        logger.critical(
            "the signing key is not fit for production: %s. Generate a JWT_SECRET_KEY and set it",
            problem,
            extra={"event": "startup.insecure_secret", "problem": problem},
        )
        raise InsecureSecretError(f"JWT_SECRET_KEY is {problem}; refusing to start in {environment}")
    logger.warning(
        "the signing key is not fit for production (%s). "
        "Starting anyway because this is development; production stops here",
        problem,
        extra={"event": "startup.insecure_secret", "problem": problem},
    )


__all__ = ["MIN_SECRET_LENGTH", "PRODUCTION", "InsecureSecretError", "require_usable_secret", "secret_problem"]
