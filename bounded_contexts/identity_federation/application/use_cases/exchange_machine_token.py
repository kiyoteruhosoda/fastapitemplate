"""機械の名乗りを、このアプリのトークンに換える前の確かめ（ADR-0082・ADR-0087）。

assay の ``client_credentials`` で得たトークンを受け取り、**許可簿にある機械なら**「振る舞う相手」の
利用者を返す。トークンの発行はプレゼンテーション層（このアプリのトークンの作り手）が行う。

⚠ **API を機械用にもう 1 面作らない。** 「利用者として振る舞うトークン」を出せば、以降は既にある API が
そのまま使える。できることは許可簿の操作と利用者の権限の重なりに絞る（発行の側で行う）。
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
        """トークンの発行者のテナントで、そのメールアドレスの有効な利用者。居なければ ``None``。"""
        ...


@dataclass(frozen=True)
class MachineEntrance:
    """機械の口の設定。宛名か許可簿が空なら口は閉じている（ADR-0082 §2 決定 4）。"""

    #: このアプリの宛名（``MACHINE_AUDIENCE``）
    audience: str
    #: 許可簿（``MACHINE_CLIENTS``）
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
    #: トークンの発行者（このアプリに登録された、有効なテナントのもの）。知らない発行者なら空
    issuer: str
    gateway: MachineTokenGateway
    actors: MachineActors

    def execute(self, token: str) -> MachineSession:
        if not self.entrance.is_open:
            # ⚠ IdP に触る前に断る（口が閉じているのに検証へ進むと、要求ごとに IdP へ往復する）
            raise MachineEntranceClosedError
        if not self.issuer:
            raise InvalidMachineTokenError
        claims = self.gateway.verify_machine_token(self.issuer, self.entrance.audience, token)
        client_id = MachineClaims.from_claims(claims).client_id
        client = find_machine_client(self.entrance.clients, client_id)
        if client is None:
            # client_id は assay が発行した公開の識別子なので残してよい（綴りの間違いと知らない相手を切り分ける）
            logger.warning("machine_client_not_registered", extra={"client_id": client_id})
            raise MachineClientNotRegisteredError(client_id)
        user_id = self.actors.active_user_id(client.acts_as)
        if user_id is None:
            logger.warning("machine_actor_not_found", extra={"client_id": client_id})
            raise MachineActorNotFoundError(client_id)
        return MachineSession(user_id=user_id, client=client)


__all__ = ["ExchangeMachineToken", "MachineActors", "MachineEntrance", "MachineSession"]
