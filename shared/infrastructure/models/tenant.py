"""テナントと、利用者の所属のモデル（ADR-0061）。

テナント 1 行が assay のテナント 1 つに当たる。発行者（``issuer``）で見分け、
クライアント ID もテナントごとに持つ（assay のクライアントはテナントごとに登録する）。

利用者の所属は ``users`` の列ではなく 1 対 1 の別表 ``user_tenants`` に持つ。
⚠ 古い移行（据え付けの ``0002``）が ``User`` のモデルで ``users`` を書くので、
列を足すと「列を足す移行」より前の段で落ちる（``user_session_boundaries`` と同じ理由）。
所属の無い利用者はシステム管理者だけ（ADR-0061 決定 3）。
"""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.infrastructure.models.tenancy import Tenancy, declared
from shared.kernel.database.db import Base


class TenantStatus(StrEnum):
    ACTIVE = "active"
    #: 止めたテナント。利用者は入れず、更新でトークンも出し直さない。
    SUSPENDED = "suspended"


# DB ネイティブ ENUM は使わない（CHECK 制約付き VARCHAR になる）
_TENANT_STATUS = sa.Enum(*(s.value for s in TenantStatus), name="tenant_status", native_enum=False)


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = declared(Tenancy.GLOBAL)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    #: URL に使う短い名前（``/t/<slug>/login``）。
    slug: Mapped[str] = mapped_column(sa.String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    #: assay のテナントの発行者。NULL は「SSO を使わない（ローカル口座だけの）テナント」。
    issuer: Mapped[str | None] = mapped_column(sa.String(255), unique=True, nullable=True)
    #: そのテナントに登録したこのアプリのクライアント ID。
    client_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        _TENANT_STATUS, nullable=False, default=TenantStatus.ACTIVE.value, server_default=TenantStatus.ACTIVE.value
    )
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE.value


class UserTenant(Base):
    """利用者の所属（1 人 1 行）。"""

    __tablename__ = "user_tenants"
    __table_args__ = declared(Tenancy.PERSONAL)

    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("tenants.id"), nullable=False, index=True)


__all__ = ["Tenant", "TenantStatus", "UserTenant"]
