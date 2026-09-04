"""起動時に SSO の設定を一度だけ確かめてログへ出す。

⚠ **秘密鍵は署名のときになって初めて読まれる。** 権限が合っていなくても起動も
設定画面の確認も通り、利用者が IdP から戻ってきた瞬間だけ失敗する——という形に
なりやすい（ADR-0025）。ここで一度読んでおくと、デプロイの直後に気付ける。

設定値そのものはログに出さない（CLAUDE.md「ログ」）。出すのは「使える／使えない」と、
使えない場合の分類だけ。
"""

from __future__ import annotations

import logging

from bounded_contexts.identity_federation.domain.exceptions import (
    SsoNotConfiguredError,
)
from bounded_contexts.identity_federation.infrastructure.client_assertion import (
    read_private_key,
)
from bounded_contexts.identity_federation.presentation.dependencies import (
    identity_provider,
)
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)


def report_sso_configuration() -> None:
    """SSO を使う設定になっているなら、実際に始められるかを確かめる。"""
    if not settings.oidc_enabled:
        return
    provider = identity_provider()
    if provider is None or not provider.is_usable:
        # 有効にしたつもりで無効、という食い違いはここでしか気付けない。
        logger.error("sso_disabled_by_configuration")
        return
    if not provider.credential.uses_private_key:
        logger.info("sso_ready")
        return
    try:
        read_private_key(provider.credential)
    except SsoNotConfiguredError:
        # 理由は read_private_key が既に書いている（例外の型だけ）。
        logger.error("sso_private_key_unreadable")
        return
    logger.info("sso_ready")


__all__ = ["report_sso_configuration"]
