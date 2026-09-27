"""利用者ごとに「どの IdP と結び付いているか」を並べる（ADR-0039）。

「入れる手段の一覧」の IdP 側の 1 行。⚠ **結び付きがあること＝入れること**である
——ローカルのパスワードを取り上げても、この行が残っていれば SSO では入れる。
"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.identity_federation.domain.repositories.federated_issuer_directory import (
    FederatedIssuerDirectory,
)


@dataclass(frozen=True)
class ListFederatedIssuers:
    directory: FederatedIssuerDirectory

    def execute(self) -> dict[int, tuple[str, ...]]:
        return self.directory.issuers_by_user()


__all__ = ["ListFederatedIssuers"]
