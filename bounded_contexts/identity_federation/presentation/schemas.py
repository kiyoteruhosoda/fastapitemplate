"""SSO ログインの Pydantic スキーマ。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from presentation.fastapi.schemas.auth import TokenResponse


class SsoProviderResponse(BaseModel):
    """ログイン画面が「SSO で入る」ボタンを出すかどうかの判断材料。

    未認証で読めるため、接続先の URL やクライアント ID は載せない。
    """

    enabled: bool
    display_name: str
    #: パスワード・パスキーの入口が開いているか（ADR-0026 決定 2）。ログイン画面は
    #: これが偽ならパスワード欄とパスキーのボタンを出さない。
    local_login_enabled: bool = True


class SsoTicketRequest(BaseModel):
    """コールバックが渡した引き換え券。"""

    ticket: str = Field(min_length=1, max_length=255)


class SsoSessionResponse(TokenResponse):
    """引き換えの結果。``redirect_to`` は SSO を始めた画面（SPA 内の経路）。"""

    redirect_to: str


__all__ = [
    "SsoProviderResponse",
    "SsoSessionResponse",
    "SsoTicketRequest",
]
