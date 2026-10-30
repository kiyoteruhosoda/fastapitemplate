"""機械の口の許可簿 1 行（ADR-0082・ADR-0087）。

1 行が「この ``client_id`` は、この利用者として振る舞い、この操作だけをしてよい」を表す。

⚠ **操作は権限コード（scope）で書く**（``item:view`` / ``note:write`` など。ADR-0087 決定 2）。
機械に出すトークンの scope は「振る舞う利用者の権限」と「許可簿の操作」の**両方にあるものだけ**になる。
書いていない操作は通らない（既定は拒否）。``operations`` が空の行は、どの操作もできない。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class MachineClient:
    """許可簿の 1 行。"""

    #: assay が発行した ``client_id``（機械トークンの ``client_id`` クレームと突き合わせる）
    client_id: str
    #: 画面・ログに出す名前（``client_id`` は人が読んでも何のアプリか分からない）
    name: str
    #: 振る舞う相手の利用者のメールアドレス（トークンの発行者のテナントの中で引く）
    acts_as: str
    #: 使ってよい操作（権限コード）
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
    """設定（JSON の配列）を許可簿にする。

    ⚠ **``client_id`` か ``acts_as`` の無い行は捨てる。** 「誰でもない誰か」として通すことはしない。
    捨てた行の機械は、名乗っても登録が無いのと同じ 401 になる。
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
