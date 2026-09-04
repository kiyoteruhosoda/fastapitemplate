"""引き換え券の SQLAlchemy 実装。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from bounded_contexts.identity_federation.domain.entities.sso_login_ticket import (
    SsoLoginTicket,
)
from bounded_contexts.identity_federation.domain.exceptions import (
    SsoTicketNotFoundError,
)
from bounded_contexts.identity_federation.infrastructure.identity_federation_models import (
    SsoLoginTicketRecord,
)
from shared.kernel.timestamps import utcnow


@dataclass(frozen=True)
class SqlSsoLoginTicketRepository:
    session: Session

    def issue(self, ticket: SsoLoginTicket) -> SsoLoginTicket:
        self.session.execute(delete(SsoLoginTicketRecord).where(SsoLoginTicketRecord.expires_at < utcnow()))
        self.session.add(
            SsoLoginTicketRecord(
                ticket_hash=ticket.ticket_hash,
                user_id=ticket.user_id,
                redirect_to=ticket.redirect_to,
                expires_at=ticket.expires_at,
            )
        )
        self.session.flush()
        return ticket

    def redeem(self, ticket_hash: str) -> SsoLoginTicket:
        record = self.session.get(SsoLoginTicketRecord, ticket_hash)
        if record is None:
            raise SsoTicketNotFoundError

        redeemed = SsoLoginTicket(
            ticket_hash=record.ticket_hash,
            user_id=record.user_id,
            redirect_to=record.redirect_to,
            expires_at=record.expires_at,
        )

        # 券は 1 回限り。消費は削除の成否で決める（同時に 2 本送られても
        # トークンを 2 つ得られないようにする）。
        result = cast(
            "CursorResult[Any]",
            self.session.execute(
                delete(SsoLoginTicketRecord).where(SsoLoginTicketRecord.ticket_hash == ticket_hash),
                execution_options={"synchronize_session": False},
            ),
        )
        self.session.expunge(record)
        if result.rowcount != 1:
            raise SsoTicketNotFoundError
        if redeemed.is_expired(utcnow()):
            raise SsoTicketNotFoundError
        return redeemed


__all__ = ["SqlSsoLoginTicketRepository"]
