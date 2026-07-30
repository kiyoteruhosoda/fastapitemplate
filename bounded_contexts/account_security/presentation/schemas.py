"""アカウントセキュリティ API の Pydantic スキーマ。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TwoFactorStatusResponse(BaseModel):
    enabled: bool
    enrolling: bool


class TotpEnrollmentResponse(BaseModel):
    # 認証アプリに手入力するための共有鍵
    secret: str
    otpauth_uri: str
    # QR コード（SVG の data URI）。読み取り用。
    qr_code: str


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class PasskeyResponse(BaseModel):
    id: int
    name: str
    transports: list[str] = []
    created_at: str | None = None
    last_used_at: str | None = None


class PasskeyChallengeResponse(BaseModel):
    challenge_id: str
    # ブラウザの navigator.credentials へそのまま渡す WebAuthn オプション
    public_key: dict[str, Any]


class PasskeyRegistrationRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=100)


class PasskeyAuthenticationRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]


__all__ = [
    "PasskeyAuthenticationRequest",
    "PasskeyChallengeResponse",
    "PasskeyRegistrationRequest",
    "PasskeyResponse",
    "TotpCodeRequest",
    "TotpEnrollmentResponse",
    "TwoFactorStatusResponse",
]
