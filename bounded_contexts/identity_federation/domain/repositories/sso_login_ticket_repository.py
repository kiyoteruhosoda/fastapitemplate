"""Persistence interface for redemption tickets (implemented in Infrastructure)."""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.entities.sso_login_ticket import (
    SsoLoginTicket,
)


class SsoLoginTicketRepository(Protocol):
    def issue(self, ticket: SsoLoginTicket) -> SsoLoginTicket:
        """Save the ticket. Expired ones are cleaned up at this opportunity."""

    def redeem(self, ticket_hash: str) -> SsoLoginTicket:
        """Take out the ticket and discard it (single use).

        If not found or expired,
        :class:`~bounded_contexts.identity_federation.domain.exceptions.SsoTicketNotFoundError`.
        """


__all__ = ["SsoLoginTicketRepository"]
