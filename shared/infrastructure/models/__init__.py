"""Shared SQLAlchemy models.

When adding a model, add its import here so Alembic autogenerate and the tests see every table
(context-specific models are imported in ``migrations/env.py`` and ``tests/conftest.py``).
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
