"""assay の名簿を引く実装（ADR-0043）。

⚠ **引けなかったことを「空」で返さない。** 空の名簿を返すと、呼び出し側は
「全員辞めた」と読んでしまう。
"""

from __future__ import annotations

import httpx
import pytest

from bounded_contexts.identity_federation.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
)
from bounded_contexts.identity_federation.domain.value_objects.roster import RosterState
from bounded_contexts.identity_federation.infrastructure.httpx_roster_gateway import (
    SUBJECTS_PER_REQUEST,
    HttpxRosterGateway,
)

_ISSUER = "https://identity.example.test/tenant"


class _Tokens:
    def __init__(self) -> None:
        self.invalidated = False

    def token(self) -> str:
        return "machine-token"

    def invalidate(self) -> None:
        self.invalidated = True


class _Assay:
    """``httpx.get`` の代わり。呼ばれた URL と ``subs`` を覚えて、決め打ちの応答を返す。"""

    def __init__(self, status: int = 200, body: object | None = None, *, broken: bool = False) -> None:
        self.status = status
        self.body: object = {"users": []} if body is None else body
        self.broken = broken
        self.calls: list[tuple[str, str]] = []

    def get(self, url: str, *, params: dict[str, str], headers: dict[str, str], timeout: float) -> httpx.Response:
        self.calls.append((url, params.get("subs", "")))
        if self.broken:
            raise httpx.ConnectError("refused")
        return httpx.Response(self.status, json=self.body)


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "app-login")
    monkeypatch.setenv("MACHINE_CLIENT_ID", "app-machine")


def _gateway(assay: _Assay, monkeypatch: pytest.MonkeyPatch, tokens: _Tokens | None = None) -> HttpxRosterGateway:
    monkeypatch.setattr(httpx, "get", assay.get)
    return HttpxRosterGateway(tokens=tokens or _Tokens())


def test_the_path_asks_for_the_callers_own_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠ どのアプリの名簿かは assay が名乗りから決める。経路で申告しない。"""
    assay = _Assay()

    _gateway(assay, monkeypatch).fetch(subjects=("a",))

    url, subs = assay.calls[0]
    assert url == f"{_ISSUER}/admin/applications/self/users"
    assert subs == "a"
    assert "app-login" not in url
    assert "app-machine" not in url


def test_the_states_are_read_from_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    assay = _Assay(body={"users": [{"sub": "a", "state": "blocked"}, {"sub": "b", "state": "unknown"}, "junk"]})

    roster = _gateway(assay, monkeypatch).fetch(subjects=("a", "b"))

    assert roster.state_of("a") is RosterState.BLOCKED
    assert roster.state_of("b") is RosterState.UNKNOWN


def test_many_subjects_are_asked_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠ 上限を超えると 400 になる。"""
    assay = _Assay()
    subjects = tuple(f"s{index}" for index in range(SUBJECTS_PER_REQUEST + 1))

    _gateway(assay, monkeypatch).fetch(subjects=subjects)

    assert [len(subs.split(",")) for _, subs in assay.calls] == [SUBJECTS_PER_REQUEST, 1]


def test_a_403_means_the_machine_is_not_bound_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠ 結び付けるまで毎周回返る。障害（warning）と分けて知らせる。"""
    with pytest.raises(MachineNotBoundToApplicationError):
        _gateway(_Assay(status=403), monkeypatch).fetch(subjects=("a",))


@pytest.mark.parametrize("status", [404, 500, 502])
def test_other_failures_are_not_an_empty_roster(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(IdentityProviderUnavailableError):
        _gateway(_Assay(status=status), monkeypatch).fetch(subjects=("a",))


def test_a_401_forgets_the_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """期限内でも、向こうでクライアントを止めた・鍵を替えたときは通らなくなる。"""
    tokens = _Tokens()

    with pytest.raises(IdentityProviderUnavailableError):
        _gateway(_Assay(status=401), monkeypatch, tokens).fetch(subjects=("a",))

    assert tokens.invalidated


def test_an_unreachable_assay_is_not_an_empty_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(IdentityProviderUnavailableError):
        _gateway(_Assay(broken=True), monkeypatch).fetch(subjects=("a",))


def test_an_answer_without_users_is_not_an_empty_roster(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(IdentityProviderUnavailableError):
        _gateway(_Assay(body={"items": []}), monkeypatch).fetch(subjects=("a",))
