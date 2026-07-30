"""パスキーの永続化インターフェース（実装は Infrastructure 層）。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bounded_contexts.account_security.domain.entities.passkey_credential import (
    PasskeyCredential,
)


class PasskeyCredentialRepository(Protocol):
    def list_for_user(self, user_id: int) -> Sequence[PasskeyCredential]:
        """*user_id* が登録したパスキーを登録順に返す。"""

    def find_by_credential_id(self, credential_id: str) -> PasskeyCredential | None:
        """資格情報 ID からパスキーを引く（認証時に使う）。"""

    def add(self, credential: PasskeyCredential) -> PasskeyCredential:
        """パスキーを登録する。

        同じ資格情報 ID が**他人の**アカウントに存在する場合は
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyAlreadyRegisteredError`
        を送出する。本人の再登録は上書きとして扱う。
        """

    def update_usage(self, credential: PasskeyCredential) -> PasskeyCredential:
        """認証成功後の署名カウンタ・最終使用日時を反映する。"""

    def delete(self, user_id: int, passkey_id: int) -> None:
        """*user_id* が所有するパスキーを削除する。無ければ
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyNotFoundError`。
        """


__all__ = ["PasskeyCredentialRepository"]
