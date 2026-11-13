"""Pydantic schemas of the account security API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TwoFactorStatusResponse(BaseModel):
    enabled: bool
    enrolling: bool
    # Whether the app's settings make it mandatory (ADR-0093). When true, the screen offers no way to remove it
    required: bool = False


class TotpEnrollmentResponse(BaseModel):
    # Shared key for manual entry into the authenticator app
    secret: str
    otpauth_uri: str
    # QR code (an SVG data URI), for scanning.
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
    # WebAuthn options passed as is to the browser's navigator.credentials
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
