"""利用者（``users``）への窓口の SQLAlchemy 実装。

``shared`` の ``User`` / ``Role`` モデルへ触れるのはここだけで、ID 連携の
Domain / Application 層はこの実装を知らない。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from bounded_contexts.identity_federation.domain.entities.federated_account import (
    FederatedAccount,
    NewFederatedAccount,
)
from shared.infrastructure.models import Role, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SqlFederatedUserDirectory:
    session: Session

    def find_by_id(self, user_id: int) -> FederatedAccount | None:
        return _as_account(self.session.get(User, user_id))

    def find_by_email(self, email: str) -> FederatedAccount | None:
        """メールアドレスで引く。**綴りどおりの行を先に、無ければ大小を無視して**引く。

        ⚠ **``==`` だけで引かない。** PostgreSQL は大小を区別するので、``Claude@nolumia.com``
        として作られた利用者に ``claude@nolumia.com`` では届かない。idp が返すメールも、
        機械の ``acts_as`` も、こちらで作った行と綴りが一致する保証は無い。

        ⚠ **大小を無視すると 1 行に決まらないことがある。** ``users.email`` の一意制約は
        大小を区別するため、``Alice@…`` と ``alice@…`` は両方作れる（管理画面は綴りどおりに
        保存する）。そのとき「最初の 1 行」を黙って返すと、機械が振る舞う相手や SSO で
        結び付ける相手が実行計画しだいで変わる。**決まらなければ「居ない」として断る**
        （ログに残す。値は出さない）。
        """
        exact = self.session.scalar(select(User).where(User.email == email))
        if exact is not None:
            return _as_account(exact)
        normalized = email.strip().lower()
        matches = self.session.scalars(select(User).where(func.lower(User.email) == normalized)).all()
        if len(matches) > 1:
            logger.warning("federated_email_ambiguous", extra={"matches": len(matches)})
            return None
        return _as_account(matches[0] if matches else None)

    def provision(self, account: NewFederatedAccount) -> FederatedAccount:
        user = User(
            email=account.email,
            username=account.username,
            # ⚠ **ランダム値で埋めない**（ADR-0038）。埋めると「パスワードが無い」と
            # 「誰も知らないパスワードがある」が区別できなくなり、画面に変更の導線が
            # 出る・監査で入れる手段が読めない、という歪みが出る。
            password_hash=None,
            is_active=True,
        )
        user.roles = self._roles_named(account.roles)
        self.session.add(user)
        self.session.flush()
        logger.info("sso_user_provisioned")
        return _require_account(user)

    def refresh_profile(self, user_id: int, *, email: str | None, username: str) -> None:
        """名前とメールアドレスを写しへ上書きする（ADR-0042）。

        ⚠ **ぶつかる値は書かない。** ``users.email`` も ``users.username`` も一意なので、
        別の利用者が既に持っている値をそのまま書くと**ログインが 500 で落ちる**。
        写しの更新でログインを壊すのは本末転倒なので、その項目だけ見送って記録に残す。
        """
        user = self.session.get(User, user_id)
        if user is None:  # pragma: no cover - 直前に引けた利用者が消えた場合のみ
            return
        if email is not None and email != user.email and self._is_free(User.email, email, user_id):
            user.email = email
        if username and username != user.username and self._is_free(User.username, username, user_id):
            user.username = username
        self.session.flush()

    def _is_free(self, column: InstrumentedAttribute[str], value: str, user_id: int) -> bool:
        taken = self.session.scalar(select(User.id).where(column == value).where(User.id != user_id))
        if taken is not None:
            # ⚠ 値そのものは残さない（PII）。どの項目が見送られたかだけ分かればよい。
            logger.warning("federated_profile_conflict", extra={"field": column.key})
            return False
        return True

    def apply_roles(self, user_id: int, roles: Sequence[str]) -> FederatedAccount:
        user = self.session.get(User, user_id)
        if user is None:
            raise LookupError(user_id)
        resolved = self._roles_named(roles)
        if not resolved:
            # 1 つも当たらないときは触らない。グループのクレーム名を書き損じた
            # だけで全員が権限を失う（管理画面へ誰も入れなくなる）のを避ける。
            logger.warning("sso_role_sync_skipped_no_match")
            return _require_account(user)
        user.roles = resolved
        self.session.flush()
        return _require_account(user)

    def _roles_named(self, names: Sequence[str]) -> list[Role]:
        """名前でロールを引く。存在しない名前は黙って捨てる。"""
        if not names:
            return []
        return list(self.session.scalars(select(Role).where(Role.name.in_(list(names)))))


def _as_account(user: User | None) -> FederatedAccount | None:
    return None if user is None else _require_account(user)


def _require_account(user: User) -> FederatedAccount:
    return FederatedAccount(
        user_id=user.id,
        email=user.email,
        is_active=user.is_active,
        roles=user.role_names,
    )


__all__ = ["SqlFederatedUserDirectory"]
