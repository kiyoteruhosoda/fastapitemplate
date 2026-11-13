"""One row of the machine endpoint allowlist (ADR-0082, ADR-0087).

A row means "this ``client_id`` may act as this user and perform only these operations".

⚠ **Operations are written as permission codes (scopes)** (``item:view`` / ``note:write`` etc. ADR-0087 decision 2).
The scope of a token issued to a machine is **only what is in both** "the acting user's permissions" and
"the allowlist's operations".
Operations not listed don't pass (deny by default). A row with empty ``operations`` can do nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class MachineClient:
    """One allowlist row."""

    #: ``client_id`` issued by assay (matched against the machine token's ``client_id`` claim)
    client_id: str
    #: Name shown on screens and in logs (a ``client_id`` doesn't tell a human which app it is)
    name: str
    #: Email of the user to act as (looked up within the token issuer's tenant)
    acts_as: str
    #: Allowed operations (permission codes)
    operations: frozenset[str]

    def allows(self, operation: str) -> bool:
        return operation in self.operations


def _text(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    return value.strip() if isinstance(value, str) else ""


def _operations(entry: Mapping[str, object]) -> frozenset[str]:
    raw = entry.get("operations")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(item.strip() for item in raw if isinstance(item, str) and item.strip())


def parse_machine_clients(raw: Sequence[object]) -> tuple[MachineClient, ...]:
    """Turn the setting (a JSON array) into the allowlist.

    ⚠ **Rows without ``client_id`` or ``acts_as`` are dropped.** Nothing passes as "someone who is nobody".
    Machines of dropped rows get the same 401 as an unregistered one.
    """
    clients: list[MachineClient] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        client_id = _text(entry, "client_id")
        acts_as = _text(entry, "acts_as")
        if not client_id or not acts_as:
            continue
        clients.append(
            MachineClient(
                client_id=client_id,
                name=_text(entry, "name") or client_id,
                acts_as=acts_as,
                operations=_operations(entry),
            )
        )
    return tuple(clients)


def find_machine_client(clients: Sequence[MachineClient], client_id: str) -> MachineClient | None:
    return next((client for client in clients if client.client_id == client_id), None)


__all__ = ["MachineClient", "find_machine_client", "parse_machine_clients"]
