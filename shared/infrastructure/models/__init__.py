"""共有 SQLAlchemy モデル。

Alembic autogenerate・テストが全テーブルを認識できるよう、モデル追加時は
ここへ import を追加する（コンテキスト固有モデルは ``migrations/env.py`` と
``tests/conftest.py`` 側で import する）。
"""

from shared.infrastructure.models.group import UserGroup, user_group_members
from shared.infrastructure.models.log import Log
from shared.infrastructure.models.role import Permission, Role, role_permissions
from shared.infrastructure.models.system_setting import SystemSetting
from shared.infrastructure.models.tenant import RoleTenant, Tenant, TenantStatus, UserTenant
from shared.infrastructure.models.user import PasswordResetToken, RefreshSession, User, UserSessionBoundary, user_roles

__all__ = [
    "Log",
    "PasswordResetToken",
    "Permission",
    "RefreshSession",
    "Role",
    "RoleTenant",
    "SystemSetting",
    "Tenant",
    "TenantStatus",
    "User",
    "UserGroup",
    "UserSessionBoundary",
    "UserTenant",
    "role_permissions",
    "user_group_members",
    "user_roles",
]
