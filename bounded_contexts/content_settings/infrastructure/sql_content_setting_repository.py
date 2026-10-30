"""``IContentSettingRepository`` の SQLAlchemy 実装。テナントはコンストラクタで受け取る（ADR-0079 §1 決定 5）。"""

from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from bounded_contexts.content_settings.domain.repositories.content_setting_repository import (
    IContentSettingRepository,
)
from bounded_contexts.content_settings.infrastructure.content_setting_model import ContentSettingModel


class SqlContentSettingRepository(IContentSettingRepository):
    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _row(self, key: str) -> ContentSettingModel | None:
        return self._session.scalar(
            select(ContentSettingModel).where(
                ContentSettingModel.tenant_id == self._tenant_id, ContentSettingModel.key == key
            )
        )

    def stored(self) -> Mapping[str, object]:
        rows = self._session.scalars(
            select(ContentSettingModel).where(ContentSettingModel.tenant_id == self._tenant_id)
        ).all()
        return {row.key: json.loads(row.value) for row in rows}

    def put(self, key: str, value: str | bool | int) -> None:
        encoded = json.dumps(value)
        row = self._row(key)
        if row is None:
            self._session.add(ContentSettingModel(tenant_id=self._tenant_id, key=key, value=encoded))
        else:
            row.value = encoded
        self._session.flush()

    def remove(self, key: str) -> None:
        self._session.execute(
            delete(ContentSettingModel).where(
                ContentSettingModel.tenant_id == self._tenant_id, ContentSettingModel.key == key
            )
        )
        self._session.flush()


__all__ = ["SqlContentSettingRepository"]
