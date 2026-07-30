"""管理 API の Pydantic スキーマ。"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    roles: list[str]


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


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    permissions: list[str] = []


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    permissions: list[str] | None = None


class PermissionResponse(BaseModel):
    id: int
    code: str


class SystemSettingItemResponse(BaseModel):
    key: str
    category: str
    label: str
    value_type: str
    secret: bool = False
    # 選択肢を持つ項目のみ。[値, 表示ラベル] の並び。
    choices: list[list[str]] | None = None
    # 反映に再起動が必要なサービス（空 = 保存と同時に反映）
    restart_scopes: list[str] = []
    value: object = None
    default: object = None
    env_locked: bool
    stored: bool


class SystemSettingsUpdateRequest(BaseModel):
    # key -> 新しい値（null でその key の DB 上書きを削除しデフォルトへ戻す）
    values: dict[str, object]


class RestartRequirementResponse(BaseModel):
    """保存した設定のうち、反映に再起動が必要なもの。"""

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
    # 省略時は全サービスが対象
    scopes: list[str] | None = None
    reason: str | None = None


class RestartCommandResponse(BaseModel):
    requested: bool
    requests: list[RestartRequestResponse]


class LogEntryResponse(BaseModel):
    id: int
    created_at: str
    level: str
    logger: str
    message: str
    request_id: str | None
    user_id_hash: str | None
    path: str | None
    method: str | None
    status_code: int | None
    duration_ms: int | None
    trace: str | None
