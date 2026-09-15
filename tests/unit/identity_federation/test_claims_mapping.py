"""クレーム -> 利用者の写し（ADR-0042 / idp の ADR-0049 G5・G7）。

⚠ **メールアドレスは鍵ではないので、無くても成立する。** 弾いていたのは鍵に
していた名残で、無いと困るのは「初回に寄せるとき」と「利用者を作るとき」だけである。
"""

from __future__ import annotations

import pytest

from bounded_contexts.identity_federation.domain.exceptions import InvalidIdTokenError
from bounded_contexts.identity_federation.domain.value_objects.claims_mapping import (
    ClaimsMapping,
)


def test_a_token_without_a_subject_is_not_a_token() -> None:
    with pytest.raises(InvalidIdTokenError):
        ClaimsMapping().apply({"email": "someone@example.com"})


def test_an_email_is_read_and_lowercased() -> None:
    user = ClaimsMapping().apply({"sub": "s", "email": "Someone@Example.COM"})
    assert user.email == "someone@example.com"


def test_a_token_without_an_email_still_names_a_user() -> None:
    """⚠ **ここで弾かない**（ADR-0042）。既に結び付いている相手は ``sub`` で入れる。"""
    user = ClaimsMapping().apply({"sub": "s", "name": "誰か"})
    assert user.email is None
    assert user.subject == "s"
    assert user.username == "誰か"


def test_without_an_email_or_a_name_the_subject_becomes_the_display_name() -> None:
    """表示名が空の利用者を作るよりはよい（後から画面で直せる）。"""
    assert ClaimsMapping().apply({"sub": "abc-123"}).username == "abc-123"


def test_the_email_domain_of_a_user_without_an_email_is_empty() -> None:
    assert ClaimsMapping().apply({"sub": "s"}).email_domain == ""


def test_groups_are_not_read_at_all() -> None:
    """⚠ **グループからロールは引かない**（G7）。assay は ``groups`` を発行しない。"""
    user = ClaimsMapping().apply({"sub": "s", "email": "a@example.com", "groups": ["admins"]})
    assert not hasattr(user, "groups")
