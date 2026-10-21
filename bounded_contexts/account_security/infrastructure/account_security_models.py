"""アカウントセキュリティ・コンテキストの SQLAlchemy モデル。

``migrations/env.py`` と ``tests/conftest.py`` がこのモジュールを import して
メタデータへ登録する（コンテキスト固有モデルの扱い。CLAUDE.md「DDL 管理」）。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from bounded_contexts.account_security.domain.entities.login_attempts import ATTEMPT_PURPOSES
from bounded_contexts.account_security.domain.entities.webauthn_challenge import (
    CHALLENGE_PURPOSES,
)
from shared.infrastructure.models.base import BigIntPk, utcnow
from shared.kernel.database.db import Base


class TotpSecretRecord(Base):
    """TOTP 共有鍵（ユーザー 1 人につき 1 行）。"""

    __tablename__ = "totp_secrets"

    user_id: Mapped[int] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    # NULL のあいだは「登録手続き中」。二要素認証はまだ有効ではない。
    confirmed_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class PasskeyCredentialRecord(Base):
    """WebAuthn 資格情報（パスキー）。"""

    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntPk,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # base64url 文字列。認証時はこの値で持ち主を引く。
    credential_id: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    public_key: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    sign_count: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        nullable=False,
        default=0,
    )
    transports = mapped_column(sa.JSON(), nullable=True)
    name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    attestation_format: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    aaguid: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    backup_eligible: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, default=False, server_default=sa.false()
    )
    backup_state: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False, server_default=sa.false())
    last_used_at = mapped_column(sa.DateTime(), nullable=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class WebAuthnChallengeRecord(Base):
    """発行済みチャレンジ。

    Gunicorn は複数ワーカーで動くため、発行したプロセスと検証するプロセスが
    一致しない。プロセスのメモリではなく DB に置く。
    """

    __tablename__ = "webauthn_challenges"

    challenge_id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    challenge: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    # DB ネイティブ ENUM は使わず、CHECK 付き VARCHAR にする（CLAUDE.md）
    purpose: Mapped[str] = mapped_column(
        sa.Enum(*CHALLENGE_PURPOSES, name="webauthn_challenge_purpose", native_enum=False),
        nullable=False,
    )
    # ログイン用チャレンジは発行時点で相手が分からないため NULL 可
    user_id: Mapped[int | None] = mapped_column(BigIntPk, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    expires_at = mapped_column(sa.DateTime(), nullable=False, index=True)
    created_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow)


class LoginAttemptRecord(Base):
    """宛名ごとの失敗の控え（ADR-0058）。

    宛名は**送られてきたメールアドレス**で、``users`` とは結ばない。実在する
    アカウントだけを数えると、断られるかどうかで存在が分かってしまう。
    期限切れの行は書き込みのたびに掃除する。
    """

    __tablename__ = "login_attempts"
    __table_args__ = (sa.CheckConstraint(f"purpose IN {ATTEMPT_PURPOSES}", name="ck_login_attempts_purpose"),)

    purpose: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    identifier: Mapped[str] = mapped_column(sa.String(255), primary_key=True)
    failures: Mapped[int] = mapped_column(sa.Integer(), nullable=False, default=0, server_default="0")
    window_started_at = mapped_column(sa.DateTime(), nullable=True)
    locked_until = mapped_column(sa.DateTime(), nullable=True)
    updated_at = mapped_column(sa.DateTime(), nullable=False, default=utcnow, onupdate=utcnow)


__all__ = [
    "LoginAttemptRecord",
    "PasskeyCredentialRecord",
    "TotpSecretRecord",
    "WebAuthnChallengeRecord",
]
