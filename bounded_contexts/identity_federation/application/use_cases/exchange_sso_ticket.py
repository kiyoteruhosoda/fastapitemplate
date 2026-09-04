"""引き換え券をログイン結果へ換える（SPA からの ``POST``）。

券は 1 回限りで、消費は削除の成否で決める（同じ券を 2 本同時に送られても
トークンを 2 つ得られないようにする。パスキーのチャレンジと同じ作法）。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.application.dto.sso_dto import SsoSessionDto
from bounded_contexts.identity_federation.domain.repositories.sso_login_ticket_repository import (
    SsoLoginTicketRepository,
)
from bounded_contexts.identity_federation.domain.services.login_secrets import (
    hash_secret,
)


@dataclass(frozen=True)
class ExchangeSsoTicket:
    tickets: SsoLoginTicketRepository

    def execute(self, *, ticket: str) -> SsoSessionDto:
        redeemed = self.tickets.redeem(hash_secret(ticket))
        return SsoSessionDto(user_id=redeemed.user_id, redirect_to=redeemed.redirect_to)


__all__ = ["ExchangeSsoTicket"]
