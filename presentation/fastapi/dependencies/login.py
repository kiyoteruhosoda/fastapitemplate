"""ログイン検証の ``Depends()`` 用依存関数。

DB セッション・第二要素の検証・監査記録を組み立てて
:class:`~presentation.fastapi.services.login_service.LoginService` に注入する。
ルーターはこれを 1 つ受け取るだけで済み、認証の材料を個別に知らなくてよい。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.presentation import dependencies as security
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.services.login_service import LoginService
from shared.kernel.database.session import get_db


def get_login_service(
    db: Annotated[Session, Depends(get_db)],
    second_factor: Annotated[VerifySecondFactor, Depends(security.verify_second_factor)],
    audit: AuditRecorderDep,
) -> LoginService:
    return LoginService(db=db, second_factor=second_factor, audit=audit)


LoginServiceDep = Annotated[LoginService, Depends(get_login_service)]

__all__ = ["LoginServiceDep", "get_login_service"]
