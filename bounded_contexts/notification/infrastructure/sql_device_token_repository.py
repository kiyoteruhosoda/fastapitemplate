"""``IDeviceTokenRepository`` の SQLAlchemy 実装（ADR-0049）。"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from sqlalchemy.orm import Session

from bounded_contexts.notification.domain.entities.device_token import DeviceToken
from bounded_contexts.notification.domain.repositories.device_token_repository import IDeviceTokenRepository
from bounded_contexts.notification.infrastructure.notification_models import AppDeviceTokenModel
from shared.kernel.timestamps import utcnow


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SqlDeviceTokenRepository(IDeviceTokenRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, device: DeviceToken) -> None:
        row = self._session.scalar(
            sa.select(AppDeviceTokenModel).where(AppDeviceTokenModel.token_sha256 == _digest(device.token))
        )
        if row is None:
            row = AppDeviceTokenModel(token_sha256=_digest(device.token), token=device.token)
            self._session.add(row)
        row.user_id = device.user_id
        row.platform = device.platform
        # 中身が同じでも登録し直した時刻は残す（onupdate は値が変わらないと動かない）。
        row.updated_at = utcnow()
        self._session.flush()

    def remove(self, user_id: int, token: str) -> None:
        self._session.execute(
            sa.delete(AppDeviceTokenModel)
            .where(AppDeviceTokenModel.token_sha256 == _digest(token))
            .where(AppDeviceTokenModel.user_id == user_id)
        )

    def remove_token(self, token: str) -> None:
        self._session.execute(sa.delete(AppDeviceTokenModel).where(AppDeviceTokenModel.token_sha256 == _digest(token)))

    def for_users(self, user_ids: list[int]) -> list[DeviceToken]:
        if not user_ids:
            return []
        rows = self._session.scalars(
            sa.select(AppDeviceTokenModel)
            .where(AppDeviceTokenModel.user_id.in_(user_ids))
            .order_by(AppDeviceTokenModel.id)
        ).all()
        return [DeviceToken(user_id=r.user_id, token=r.token, platform=r.platform) for r in rows]


__all__ = ["SqlDeviceTokenRepository"]
