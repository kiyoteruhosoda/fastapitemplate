"""Public API that serves the initial UI settings.

Operators set the default language and theme in the admin console (system_settings), but the
browser applies them. They are needed on screens before login too, so no auth is required.

A language or theme the user picked takes precedence from the browser's ``localStorage``; this
only returns "the defaults when nothing has been chosen yet" and "the options".
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
