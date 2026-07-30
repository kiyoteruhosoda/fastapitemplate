"""モデル共通の型・関数。

- 主キー等の ``BigInteger`` は SQLite テストとの両立のため
  ``with_variant(sa.Integer(), "sqlite")`` を使う（CLAUDE.md「DB モデリング」）。
- 時刻は常に UTC（naive datetime で保存する）。生成は
  :func:`shared.kernel.timestamps.utcnow` に集約する。
"""

from __future__ import annotations

import sqlalchemy as sa

from shared.kernel.timestamps import utcnow

BigIntPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


__all__ = ["BigIntPk", "utcnow"]
