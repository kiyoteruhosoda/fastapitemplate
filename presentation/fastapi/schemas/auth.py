"""認証系の Pydantic スキーマ。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # 二要素認証が有効なアカウントでのみ必須（未提示なら totp_required を返す）
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    username: str
    scopes: list[str]


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
