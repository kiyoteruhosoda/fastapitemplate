"""Pydantic schemas for the admin API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SignInEntrancesResponse(BaseModel):
    """The ways this user can **sign in to this app** (ADR-0076 §7).

    ⚠ **An inventory value that assumes two authentication systems.** Requiring MFA on the IdP
    side does not apply to this app's password or passkeys. How many entrances are open is only
    visible side by side.
    """

    #: Whether password sign-in is possible (``users.password_hash`` is not NULL; ADR-0076 §6).
    password: bool = False
    #: Whether this app's two-factor auth (TOTP) is enabled. **Separate from IdP-side MFA.**
    totp: bool = False
    #: Number of passkeys registered in this app. **Separate from IdP-side passkeys.**
    passkeys: int = 0
    #: Issuers of linked IdPs. Empty = cannot sign in via SSO.
    identity_providers: list[str] = []


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    roles: list[str]
    #: Sign-in methods (ADR-0076 §7). Same shape for list, create and update.
    entrances: SignInEntrancesResponse = SignInEntrancesResponse()


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)
    roles: list[str] = []


class UserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    roles: list[str] | None = None
    password: str | None = Field(default=None, min_length=8)


class RoleResponse(BaseModel):
    id: int
    name: str
    permissions: list[str]
    #: Template shared by all tenants (cannot be modified; ADR-0079 §3)
    shared: bool = False


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    permissions: list[str] = []


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    permissions: list[str] | None = None


class GroupMemberResponse(BaseModel):
    id: int
    username: str
    #: Not returned to readers without ``group:manage`` (nolumiatask #785)
    email: str | None


class GroupResponse(BaseModel):
    id: int
    name: str
    description: str
    members: list[GroupMemberResponse]


class GroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    member_ids: list[int] = []


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    member_ids: list[int] | None = None


class PermissionResponse(BaseModel):
    id: int
    code: str


class SystemStatusResponse(BaseModel):
    version: str
    git_sha: str
    branch: str
    build_time: str
    environment: str
    # key = component name (api / database), value = "ok" | "ng"
    components: dict[str, str]
    uptime_seconds: float
    timestamp_utc: str


class SystemSettingItemResponse(BaseModel):
    key: str
    category: str
    label: str
    value_type: str
    secret: bool = False
    # Only for items with options. A list of [value, display label].
    choices: list[list[str]] | None = None
    # Services that need a restart to apply (empty = applied on save)
    restart_scopes: list[str] = []
    # Set only by environment variables (read-only; ADR-0090)
    env_only: bool = False
    value: object = None
    default: object = None
    env_fallback: bool
    stored: bool


class SystemSettingsUpdateRequest(BaseModel):
    # key -> new value (null deletes that key's DB override and reverts to the default)
    values: dict[str, object]


class RestartRequirementResponse(BaseModel):
    """Saved settings that need a restart to take effect."""

    scopes: list[str] = []
    keys: list[str] = []


class SystemSettingsUpdateResponse(BaseModel):
    status: str
    restart_required: RestartRequirementResponse | None = None


class RestartRequestResponse(BaseModel):
    scope: str
    token: str
    requested_at: str | None = None
    requested_by: str | None = None
    reason: str | None = None


class RestartStatusResponse(BaseModel):
    available_scopes: list[str]
    last_requests: list[RestartRequestResponse]


class RestartCommandRequest(BaseModel):
    # If omitted, all services are targeted
    scopes: list[str] | None = None
    reason: str | None = None


class RestartCommandResponse(BaseModel):
    requested: bool
    requests: list[RestartRequestResponse]
