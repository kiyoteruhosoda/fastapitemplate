"""画面の初期設定を配る公開 API。

言語・テーマの既定値は管理画面（system_settings）で運用者が決めるが、実際に
適用するのはブラウザ側。ログイン前の画面でも必要になるため認証は要求しない。

利用者が自分で選んだ言語・テーマはブラウザの ``localStorage`` が優先で、ここで
返すのは「まだ何も選んでいないときの初期値」と「選択肢」だけ。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from shared.kernel.settings.settings import settings

router = APIRouter(prefix="/api/ui", tags=["ui"])


class UiSettingsResponse(BaseModel):
    languages: list[str]
    default_locale: str
    default_theme: str


@router.get("/settings", response_model=UiSettingsResponse)
async def get_ui_settings() -> UiSettingsResponse:
    return UiSettingsResponse(
        languages=list(settings.languages),
        default_locale=settings.default_locale,
        default_theme=settings.default_theme,
    )
