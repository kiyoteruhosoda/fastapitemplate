"""機械の口の許可簿と、トークンの主体（ADR-0082 §1 決定 3・ADR-0087）。"""

from __future__ import annotations

from typing import Any

import pytest

from bounded_contexts.identity_federation.domain.exceptions import InvalidMachineTokenError
from bounded_contexts.identity_federation.domain.value_objects.machine_claims import MachineClaims
from bounded_contexts.identity_federation.domain.value_objects.machine_client import (
    find_machine_client,
    parse_machine_clients,
)


def test_rows_without_a_client_or_an_actor_are_dropped() -> None:
    clients = parse_machine_clients(
        [
            {"client_id": " robot ", "acts_as": "a@example.com", "operations": ["item:view", " ", 3]},
            {"client_id": "", "acts_as": "a@example.com"},
            {"client_id": "orphan"},
            "not a row",
        ]
    )
    assert [(c.client_id, c.name, c.operations) for c in clients] == [("robot", "robot", frozenset({"item:view"}))]


def test_missing_operations_mean_nothing_is_allowed() -> None:
    client = find_machine_client(parse_machine_clients([{"client_id": "c", "acts_as": "a@example.com"}]), "c")
    assert client is not None
    assert client.operations == frozenset()
    assert not client.allows("item:view")


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "c", "client_id": "c"},
        {"sub": "c", "client_id": "c", "sub_type": "user"},
        {"sub": "user-1", "client_id": "c", "sub_type": "client"},
        {"sub": "", "client_id": "", "sub_type": "client"},
    ],
)
def test_only_a_client_acting_as_itself_is_a_machine(claims: dict[str, Any]) -> None:
    with pytest.raises(InvalidMachineTokenError):
        MachineClaims.from_claims(claims)


def test_a_client_token_is_read() -> None:
    assert MachineClaims.from_claims({"sub": "c", "client_id": "c", "sub_type": "client"}).client_id == "c"
