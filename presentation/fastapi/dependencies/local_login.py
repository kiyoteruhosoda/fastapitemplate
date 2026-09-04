"""ローカルの入口が開いているかの確認（ADR-0026 決定 2・3）。

``LOCAL_LOGIN_ENABLED`` が ``false`` のとき、パスワード・パスキーでのログインと、
**ローカル資格情報の登録**（パスキー・TOTP・パスワード変更）を止める。

登録まで止めるのは、閉じた入口の合鍵を作れないようにするため。SSO で入った利用者が
パスキーを足せてしまうと、設定を戻した瞬間にその鍵が効く。「入口が閉じている＝その
入口の鍵は増えない」を規則にすれば、運用側は「閉じた」以上のことを考えなくてよい。

**既に登録済みの資格情報は消さない。** 閉じたときに消すと、開け直したときに全員が
締め出される。
"""

from __future__ import annotations

from fastapi import HTTPException, status

from shared.kernel.settings.settings import settings

ERROR_CODE = "local_login_disabled"


def require_local_login() -> None:
    """ローカルの入口が閉じているなら 403 で断る（``Depends()`` 用）。"""
    if not settings.local_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": ERROR_CODE},
        )


__all__ = ["ERROR_CODE", "require_local_login"]
