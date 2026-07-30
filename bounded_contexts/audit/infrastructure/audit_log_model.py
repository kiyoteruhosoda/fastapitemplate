"""``audit_log`` テーブルの SQLAlchemy モデル（audit コンテキスト固有）。

追記専用の記録なので外部キーは張らない。ユーザーを削除しても「誰が何をしたか」
の行は残らなければならないため（ADR-0010）。

Alembic とテストが認識できるよう ``migrations/env.py`` と ``tests/conftest.py``
へ import を追加してある。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bounded_contexts.audit.domain.entities.audit_event import AuditResult
from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base

# DB ネイティブ ENUM は使わない（CHECK 制約付き VARCHAR になる。CLAUDE.md「DB モデリング」）。
# 許可値は Python 側の AuditResult で集中管理する。
_AUDIT_RESULT = sa.Enum(
    *(result.value for result in AuditResult),
    name="audit_result",
    native_enum=False,
)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    occurred_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    result: Mapped[str] = mapped_column(_AUDIT_RESULT, nullable=False, index=True)
    # 操作した利用者の内部 ID。認証前の失敗（未登録メールでのログイン）では NULL。
    actor_user_id = mapped_column(BigIntPk, nullable=True, index=True)
    target_type = mapped_column(sa.String(64), nullable=True, index=True)
    target_id = mapped_column(sa.String(64), nullable=True)
    ip_address = mapped_column(sa.String(45), nullable=True)
    user_agent = mapped_column(sa.String(512), nullable=True)
    # 失敗理由・変更した項目名。値そのもの（PII）は入れない。
    reason = mapped_column(sa.String(255), nullable=True)
    # log.request_id と同じ値。アプリログと監査ログを突き合わせる追跡キー。
    request_id = mapped_column(sa.String(36), nullable=True, index=True)


__all__ = ["AuditLogModel"]
