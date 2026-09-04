"""認証系の Pydantic スキーマ。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # 二要素認証が有効なアカウントでのみ必須（未提示なら totp_required を返す）
    totp_code: str | None = None


class SessionResponse(BaseModel):
    """ログインが成立したことと、アクセストークンの寿命（ADR-0028）。

    ⚠ **トークンそのものは載せない。** Cookie で運ぶ。本文にも返すと、Cookie が
    自動で送られる以上、XSS が更新の口を叩いて新しいトークンを読めてしまう。
    ``expires_in`` は SPA が更新の頃合いを測るためだけの値。
    """

    expires_in: int


class MeResponse(BaseModel):
    user_id: int
    email: str
    username: str
    # いま有効な scope（アクティブロールで絞り込まれた後の権限）
    scopes: list[str]
    # 付与されている全ロール = 切り替えられる先の一覧（ADR-0017）
    roles: list[str]
    # None = すべてのロール（保有権限の和集合）で操作している
    active_role: str | None = None


class RoleSwitchRequest(BaseModel):
    """アクティブロールの切り替え要求。``None`` ですべてのロールへ戻す。"""

    role: str | None = None


class ProfileUpdateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class StatusResponse(BaseModel):
    status: str
