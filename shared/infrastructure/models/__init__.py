"""共有 SQLAlchemy モデル。

Alembic autogenerate・テストが全テーブルを認識できるよう、モデル追加時は
ここへ import を追加する（コンテキスト固有モデルは ``migrations/env.py`` と
``tests/conftest.py`` 側で import する）。
"""

from shared.infrastructure.models.log import Log
from shared.infrastructure.models.role import Permission, Role, role_permissions
from shared.infrastructure.models.system_setting import SystemSetting
from shared.infrastructure.models.user import PasswordResetToken, User, user_roles

__all__ = [
    "Log",
    "PasswordResetToken",
    "Permission",
    "Role",
    "SystemSetting",
    "User",
    "role_permissions",
    "user_roles",
]
