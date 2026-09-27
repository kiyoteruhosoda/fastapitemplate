"""アプリ（assay に直接ログインした Android アプリ）から叩いてよい口の**例**（ADR-0045）。

⚠ **雛形は 1 本だけ置く。** 派生のアプリで「アプリからも叩いてよい」ルータを増やすときは、
ここと同じく :data:`~bounded_contexts.identity_federation.presentation.app_bearer.AppOrWebPrincipalDep`
を付ける。付けないルータは、これまでどおりこのアプリのトークン（Web）だけを受ける。
⚠ **``APP_CLIENT_IDS`` が空なら、ここも Web のトークンしか受けない。**
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
    # 権限は毎回 DB から引く（assay のトークンには載っていない）
    scopes: list[str]


@router.get("/me", response_model=AppMeResponse)
async def app_me(principal: AppOrWebPrincipalDep) -> AppMeResponse:
    """いま誰として叩いているか。アプリがログインの直後に 1 回呼んで、口座ができたことを確かめる。"""
    return AppMeResponse(
        user_id=principal.user_id,
        email=principal.email,
        username=principal.username,
        scopes=sorted(principal.permissions),
    )


__all__ = ["router"]
