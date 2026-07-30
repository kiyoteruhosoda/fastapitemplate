"""WebAuthn の Relying Party 操作インターフェース（実装は Infrastructure 層）。

ブラウザとやり取りする JSON は素の ``dict`` として扱い、WebAuthn ライブラリの
型をドメイン・アプリケーション層へ持ち込まない。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PublicKeyOptions:
    """ブラウザの ``navigator.credentials`` に渡すオプションとチャレンジ。"""

    public_key: dict[str, Any]
    challenge: str


@dataclass(frozen=True)
class VerifiedRegistration:
    """登録レスポンスの検証結果。"""

    credential_id: str
    public_key: str
    sign_count: int
    attestation_format: str | None
    aaguid: str | None
    backup_eligible: bool
    backup_state: bool


@dataclass(frozen=True)
class VerifiedAssertion:
    """認証レスポンスの検証結果。"""

    credential_id: str
    sign_count: int


class WebAuthnRelyingParty(Protocol):
    def create_registration_options(
        self,
        *,
        user_id: int,
        user_name: str,
        display_name: str,
        exclude_credential_ids: Sequence[str] = (),
    ) -> PublicKeyOptions:
        """パスキー登録用のオプションを組み立てる。"""

    def verify_registration(self, *, credential: Mapping[str, Any], expected_challenge: str) -> VerifiedRegistration:
        """登録レスポンスを検証する。失敗時は
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyVerificationError`。
        """

    def create_authentication_options(self, *, allow_credential_ids: Sequence[str] = ()) -> PublicKeyOptions:
        """パスキー認証用のオプションを組み立てる。

        ``allow_credential_ids`` が空なら、認証器が自分で資格情報を選ぶ
        （ユーザー名を入力しないログイン）。
        """

    def verify_authentication(
        self,
        *,
        credential: Mapping[str, Any],
        expected_challenge: str,
        stored_public_key: str,
        stored_sign_count: int,
    ) -> VerifiedAssertion:
        """認証レスポンスを検証する。失敗時は
        :class:`~bounded_contexts.account_security.domain.exceptions.PasskeyVerificationError`。
        """

    def extract_credential_id(self, credential: Mapping[str, Any]) -> str | None:
        """レスポンスから資格情報 ID を取り出す（検証前に保存済みの鍵を引くため）。"""


__all__ = [
    "PublicKeyOptions",
    "VerifiedAssertion",
    "VerifiedRegistration",
    "WebAuthnRelyingParty",
]
