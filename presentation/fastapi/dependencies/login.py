"""``Depends()`` dependency for login verification.

Assembles the DB session, second-factor verification and audit recording and injects them into
:class:`~presentation.fastapi.services.login_service.LoginService`.
Routers just take this one dependency and need not know the individual auth pieces.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from bounded_contexts.account_security.application.use_cases.throttle_login import ThrottleLogin
from bounded_contexts.account_security.application.use_cases.verify_second_factor import (
    VerifySecondFactor,
)
from bounded_contexts.account_security.presentation import dependencies as security
from bounded_contexts.audit.presentation.dependencies import AuditRecorderDep
from presentation.fastapi.services.login_service import LoginChecks, LoginService
from shared.kernel.database.session import get_db


def get_login_service(
    db: Annotated[Session, Depends(get_db)],
    second_factor: Annotated[VerifySecondFactor, Depends(security.verify_second_factor)],
    throttle: Annotated[ThrottleLogin, Depends(security.throttle_login)],
    audit: AuditRecorderDep,
) -> LoginService:
    return LoginService(db=db, checks=LoginChecks(second_factor=second_factor, throttle=throttle), audit=audit)


LoginServiceDep = Annotated[LoginService, Depends(get_login_service)]

__all__ = ["LoginServiceDep", "get_login_service"]
