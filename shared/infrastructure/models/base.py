"""モデル共通の型・関数。

- 主キー等の ``BigInteger`` は SQLite テストとの両立のため
  ``with_variant(sa.Integer(), "sqlite")`` を使う（CLAUDE.md「DB モデリング」）。
- 時刻は常に UTC（naive datetime で保存する）。
"""
from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

BigIntPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


__all__ = ["BigIntPk", "utcnow"]
