"""WebAuthn Relying Party の実装（``webauthn`` / py_webauthn）。

ライブラリの型はこのモジュールの外へ出さない。オプションは JSON へ落として
``dict`` で返し、検証結果はドメインの値オブジェクトへ詰め替える。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from bounded_contexts.account_security.domain.exceptions import (
    PasskeyVerificationError,
)
from bounded_contexts.account_security.domain.services.webauthn_relying_party import (
    PublicKeyOptions,
    VerifiedAssertion,
    VerifiedRegistration,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PyWebAuthnRelyingParty:
    rp_id: str
    rp_name: str
    origin: str

    # ------------------------------------------------------------------
    # 登録
    # ------------------------------------------------------------------

    def create_registration_options(
        self,
        *,
        user_id: int,
        user_name: str,
        display_name: str,
        exclude_credential_ids: Sequence[str] = (),
    ) -> PublicKeyOptions:
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=str(user_id).encode("utf-8"),
            user_name=user_name,
            user_display_name=display_name,
            attestation=AttestationConveyancePreference.NONE,
            authenticator_selection=AuthenticatorSelectionCriteria(
                # ログインは資格情報を指定せずに始める（メールアドレスの入力が
                # 要らない）。認証器が自分で選べる形で保存されていないと、
                # 登録できても後から使えないパスキーになるため REQUIRED。
                resident_key=ResidentKeyRequirement.REQUIRED,
                # パスキーだけでログインできる＝パスワードも TOTP も通らない。
                # 端末を拾っただけで入れないよう、生体・PIN の確認を必須にする。
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=_descriptors(exclude_credential_ids),
        )
        return _to_public_key_options(options)

    def verify_registration(self, *, credential: Mapping[str, Any], expected_challenge: str) -> VerifiedRegistration:
        try:
            verified = verify_registration_response(
                credential=dict(credential),
                expected_challenge=base64url_to_bytes(expected_challenge),
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                require_user_verification=True,
            )
        except Exception as exc:
            logger.warning("パスキー登録の検証に失敗しました: %s", type(exc).__name__)
            raise PasskeyVerificationError from exc

        return VerifiedRegistration(
            credential_id=bytes_to_base64url(verified.credential_id),
            public_key=bytes_to_base64url(verified.credential_public_key),
            sign_count=verified.sign_count,
            attestation_format=_as_text(verified.fmt),
            aaguid=_as_text(verified.aaguid),
            backup_eligible=_as_text(verified.credential_device_type) == "multi_device",
            backup_state=bool(verified.credential_backed_up),
        )

    # ------------------------------------------------------------------
    # 認証
    # ------------------------------------------------------------------

    def create_authentication_options(self, *, allow_credential_ids: Sequence[str] = ()) -> PublicKeyOptions:
        options = generate_authentication_options(
            rp_id=self.rp_id,
            user_verification=UserVerificationRequirement.REQUIRED,
            allow_credentials=_descriptors(allow_credential_ids),
        )
        return _to_public_key_options(options)

    def verify_authentication(
        self,
        *,
        credential: Mapping[str, Any],
        expected_challenge: str,
        stored_public_key: str,
        stored_sign_count: int,
    ) -> VerifiedAssertion:
        try:
            verified = verify_authentication_response(
                credential=dict(credential),
                expected_challenge=base64url_to_bytes(expected_challenge),
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                credential_public_key=base64url_to_bytes(stored_public_key),
                credential_current_sign_count=stored_sign_count,
                require_user_verification=True,
            )
        except Exception as exc:
            logger.warning("パスキー認証の検証に失敗しました: %s", type(exc).__name__)
            raise PasskeyVerificationError from exc

        return VerifiedAssertion(
            credential_id=bytes_to_base64url(verified.credential_id),
            sign_count=verified.new_sign_count,
        )

    def extract_credential_id(self, credential: Mapping[str, Any]) -> str | None:
        value = credential.get("id")
        return value if isinstance(value, str) and value else None


def _descriptors(
    credential_ids: Sequence[str],
) -> list[PublicKeyCredentialDescriptor] | None:
    descriptors: list[PublicKeyCredentialDescriptor] = []
    for credential_id in credential_ids:
        try:
            descriptors.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(credential_id)))
        except Exception:
            # 壊れたレコードのために発行そのものを失敗させない
            logger.debug("資格情報 ID を復号できませんでした", exc_info=True)
    return descriptors or None


def _to_public_key_options(options: Any) -> PublicKeyOptions:
    return PublicKeyOptions(
        public_key=json.loads(options_to_json(options)),
        challenge=bytes_to_base64url(options.challenge),
    )


def _as_text(value: Any) -> str | None:
    """列挙型・文字列・``None`` を素の文字列へ揃える。"""
    if value is None:
        return None
    return str(getattr(value, "value", value))


__all__ = ["PyWebAuthnRelyingParty"]
