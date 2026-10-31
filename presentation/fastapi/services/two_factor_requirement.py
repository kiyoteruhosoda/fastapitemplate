"""パスワードで入ったログインに二要素認証を求めるか（ADR-0093）。

⚠ **トークンを出すたびに決め直す。** 更新の口も通るので、設定を入れれば 5 分以内に今のログインへ効き、
登録を済ませて更新すれば外れる。
"""

from __future__ import annotations

from sqlalchemy.orm import object_session

from bounded_contexts.account_security.infrastructure.sql_local_factor_directory import (
    SqlLocalFactorDirectory,
)
from presentation.fastapi.services.session_carry_over import SessionCarryOver
from shared.infrastructure.models import User
from shared.kernel.settings.settings import settings


def needs_two_factor_setup(user: User, carry: SessionCarryOver) -> bool:
    """SSO は IdP の強度に任せ（ADR-0076 §3）、パスキーはそれだけで二要素を満たす。残るのはパスワードだけ。"""
    if not settings.local_two_factor_required or carry.federated_login is not None or carry.signed_in_with_passkey:
        return False
    session = object_session(user)
    if session is None:  # pragma: no cover - 入口は全部 DB から読んだ利用者を渡す
        raise RuntimeError("the user must belong to a session")
    return not SqlLocalFactorDirectory(session).factors_of(user.id).totp


__all__ = ["needs_two_factor_setup"]
