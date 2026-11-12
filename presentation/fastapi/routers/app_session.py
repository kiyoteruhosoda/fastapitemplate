"""An **example** endpoint that the app (an Android app logged in directly to assay) may call
(ADR-0081 §1).

⚠ **The template ships only one.** When a derived app adds routers the app may also call,
attach :data:`~bounded_contexts.identity_federation.presentation.app_bearer.AppOrWebPrincipalDep`
as done here. Routers without it keep accepting only this application's own (Web) tokens.
⚠ **If ``APP_CLIENT_IDS`` is empty, this one also accepts only Web tokens.**
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from bounded_contexts.identity_federation.presentation.app_bearer import AppOrWebPrincipalDep

router = APIRouter(prefix="/api/app", tags=["app"])


class AppMeResponse(BaseModel):
    user_id: int
    email: str
    username: str
    # Permissions are read from the DB every time (assay tokens do not carry them)
    scopes: list[str]


@router.get("/me", response_model=AppMeResponse)
def app_me(principal: AppOrWebPrincipalDep) -> AppMeResponse:
    """Who the caller currently is. The app calls this once right after login to confirm the account
    exists."""
    return AppMeResponse(
        user_id=principal.user_id,
        email=principal.email,
        username=principal.username,
        scopes=sorted(principal.permissions),
    )


__all__ = ["router"]
