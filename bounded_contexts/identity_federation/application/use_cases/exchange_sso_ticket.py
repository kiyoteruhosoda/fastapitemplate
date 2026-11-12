"""Exchange a redemption ticket for the login result (``POST`` from the SPA).

Tickets are single-use, and consumption is decided by whether the delete succeeds (so sending
the same ticket twice concurrently can't get two tokens; same approach as passkey challenges).
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
        return SsoSessionDto(
            user_id=redeemed.user_id,
            redirect_to=redeemed.redirect_to,
            login=redeemed.login,
        )


__all__ = ["ExchangeSsoTicket"]
