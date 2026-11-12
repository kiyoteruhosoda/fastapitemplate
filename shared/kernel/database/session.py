"""DB session dependency for FastAPI's ``Depends()``."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from shared.kernel.database.db import get_session_factory


def get_db() -> Generator[Session]:
    """Per-request session. Commits on normal completion and rolls back on exception.

    Example::

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
