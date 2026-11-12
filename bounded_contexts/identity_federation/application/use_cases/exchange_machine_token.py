"""Checks before exchanging a machine's identity for this app's token (ADR-0082, ADR-0087).

Receives a token obtained with assay ``client_credentials`` and, **if the machine is in the allowlist**, returns
the user to act as. Token issuance is done by the presentation layer (the maker of this app's tokens).

⚠ **Don't build a second API surface for machines.** Issuing "a token that acts as a user" lets existing APIs
be used as is. What it can do is narrowed to the overlap of allowlist operations and user permissions (done on
the issuing side).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from bounded_contexts.identity_federation.domain.exceptions import (
    InvalidMachineTokenError,
    MachineActorNotFoundError,
    MachineClientNotRegisteredError,
    MachineEntranceClosedError,
)
from bounded_contexts.identity_federation.domain.services.machine_token_gateway import MachineTokenGateway
from bounded_contexts.identity_federation.domain.value_objects.machine_claims import MachineClaims
from bounded_contexts.identity_federation.domain.value_objects.machine_client import (
    MachineClient,
    find_machine_client,
)

logger = logging.getLogger(__name__)


class MachineActors(Protocol):
    def active_user_id(self, email: str) -> int | None:
        """The active user with that email in the token issuer's tenant. ``None`` if absent."""
        ...


@dataclass(frozen=True)
class MachineEntrance:
    """Machine endpoint settings. If the audience or the allowlist is empty, the endpoint is closed
    (ADR-0082 §2 decision 4)."""

    #: This app's audience (``MACHINE_AUDIENCE``)
    audience: str
    #: Allowlist (``MACHINE_CLIENTS``)
    clients: tuple[MachineClient, ...]

    @property
    def is_open(self) -> bool:
        return bool(self.audience and self.clients)


@dataclass(frozen=True)
class MachineSession:
    user_id: int
    client: MachineClient


@dataclass(frozen=True)
class ExchangeMachineToken:
    entrance: MachineEntrance
    #: Token issuer (of an active tenant registered in this app). Empty for an unknown issuer
    issuer: str
    gateway: MachineTokenGateway
    actors: MachineActors

    def execute(self, token: str) -> MachineSession:
        if not self.entrance.is_open:
            # ⚠ Refuse before touching the IdP (proceeding to verification with the endpoint closed would round-trip
            # to the IdP per request)
            raise MachineEntranceClosedError
        if not self.issuer:
            raise InvalidMachineTokenError
        claims = self.gateway.verify_machine_token(self.issuer, self.entrance.audience, token)
        client_id = MachineClaims.from_claims(claims).client_id
        client = find_machine_client(self.entrance.clients, client_id)
        if client is None:
            # client_id is a public identifier issued by assay, so it may be recorded (tells typos from unknown parties)
            logger.warning("machine_client_not_registered", extra={"client_id": client_id})
            raise MachineClientNotRegisteredError(client_id)
        user_id = self.actors.active_user_id(client.acts_as)
        if user_id is None:
            logger.warning("machine_actor_not_found", extra={"client_id": client_id})
            raise MachineActorNotFoundError(client_id)
        return MachineSession(user_id=user_id, client=client)


__all__ = ["ExchangeMachineToken", "MachineActors", "MachineEntrance", "MachineSession"]
