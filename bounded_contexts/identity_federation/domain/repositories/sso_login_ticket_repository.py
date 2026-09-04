"""引き換え券の永続化インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.sso_login_ticket import (
    SsoLoginTicket,
)


class SsoLoginTicketRepository(Protocol):
    def issue(self, ticket: SsoLoginTicket) -> SsoLoginTicket:
        """券を保存する。期限切れのものはこの機会に掃除する。"""

    def redeem(self, ticket_hash: str) -> SsoLoginTicket:
        """券を取り出して破棄する（1 回限り）。

        見つからない・期限切れの場合は
        :class:`~bounded_contexts.identity_federation.domain.exceptions.SsoTicketNotFoundError`。
        """


__all__ = ["SsoLoginTicketRepository"]
