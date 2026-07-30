"""FastAPI の ``Depends()`` 用 DB セッション依存関数。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from shared.kernel.database.db import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """リクエスト単位のセッション。正常終了で commit、例外で rollback する。

    使用例::

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


__all__ = ["get_db"]
