"""Pydantic schemas for authentication."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Required only for accounts with two-factor auth (returns totp_required if missing)
    totp_code: str | None = None
    #: Tenant of the entrance (``/t/<slug>/login``). If absent, the common entrance (ADR-0079 §4)
    tenant: str | None = Field(default=None, max_length=50, pattern=r"^[a-z0-9-]+$")


class SessionResponse(BaseModel):
    """That login succeeded, and the access token lifetime (ADR-0076 §4).

    ⚠ **The token itself is not included.** It travels in a cookie. Since the cookie is sent
    automatically, returning it in the body too would let XSS call the refresh endpoint and read
    the new token. ``expires_in`` only lets the SPA time its refresh.
    """

    expires_in: int


class MeResponse(BaseModel):
    user_id: int
    email: str
    username: str
    # Currently effective scopes (permissions after narrowing by the active role)
    scopes: list[str]
    # All granted roles = the roles one can switch to (ADR-0078 §1)
    roles: list[str]
    # None = operating with all roles (union of held permissions)
    active_role: str | None = None
    # Whether the user has a password entrance (ADR-0076 §6). ⚠ **When false, the UI does not
    # offer password change**: it would show a user who cannot enter a "current password" a form
    # that can never succeed.
    has_password: bool = True
    # Whether sign-out goes through to the IdP (``OIDC_RP_LOGOUT_ENABLED``; default false;
    # ADR-0077 §2). Returns **the server setting, not how this session signed in**. It is only
    # true for "SSO-only apps" and "apps opened on shared devices", so it never drags in users who
    # signed in with a password (apps with local accounts keep it false).
    # **Returned by /me**, separately from SSO availability, to avoid an extra request per
    # sign-out.
    rp_logout_enabled: bool = False
    # Linked to an IdP. The IdP owns name and email, so the UI shows no input fields (ADR-0094).
    profile_managed_by_idp: bool = False
    # Until two-factor enrollment is done, only the enrollment screen is usable (ADR-0093).
    two_factor_setup_required: bool = False


class RoleSwitchRequest(BaseModel):
    """Active role switch request. ``None`` reverts to all roles."""

    role: str | None = None


class ProfileUpdateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    #: Tenant of the entrance (``/t/<slug>/login``). If absent, the common entrance (ADR-0079 §4)
    tenant: str | None = Field(default=None, max_length=50, pattern=r"^[a-z0-9-]+$")


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class StatusResponse(BaseModel):
    status: str
