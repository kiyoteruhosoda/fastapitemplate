"""機械の口（ADR-0082・ADR-0087。task #718・#721）。

assay の ``client_credentials`` のトークンを換え、許可簿の操作だけが通ることを確かめる。
IdP は差し替える（署名・期限はゲートウェイの仕事。ここでは宛名と主体と許可簿を見る）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from typing import Any

import jwt
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bounded_contexts.audit.domain.entities.audit_event import AuditEventType
from bounded_contexts.audit.infrastructure.audit_log_model import AuditLogModel
from bounded_contexts.identity_federation.domain.exceptions import InvalidMachineTokenError
from bounded_contexts.identity_federation.presentation.machine_router import machine_token_gateway
from shared.domain.auth import master_data
from tests.conftest import register_issuer, sign_in

_ISSUER = "https://idp.example.test/tenant"
_AUDIENCE = "api://fastapitemplate"
_CLIENTS = [
    # 利用者（owner）は item:manage も持つが、許可簿には読むだけを書く
    {"client_id": "robot", "name": "Robot", "acts_as": master_data.DEFAULT_ADMIN_EMAIL, "operations": ["item:view"]},
    {"client_id": "idle", "name": "Idle", "acts_as": master_data.DEFAULT_ADMIN_EMAIL, "operations": []},
    {"client_id": "ghost", "acts_as": "nobody@example.com", "operations": ["item:view"]},
]


class _StubMachineTokenGateway:
    """トークンの文字列を「どのクレームか」の名前として扱う（署名は確かめない）。"""

    def __init__(self) -> None:
        self.tokens: dict[str, dict[str, Any]] = {}

    def issue(self, client_id: str, **overrides: Any) -> str:
        claims = {
            "iss": _ISSUER,
            "sub": client_id,
            "client_id": client_id,
            "sub_type": "client",
            "aud": _AUDIENCE,
            **overrides,
        }
        token = jwt.encode({"iss": claims["iss"], "name": client_id, "n": len(self.tokens)}, "k", algorithm="HS256")
        self.tokens[token] = {k: v for k, v in claims.items() if v is not None}
        return token

    def verify_machine_token(self, issuer: str, audience: str, token: str) -> Mapping[str, Any]:
        assert issuer == _ISSUER
        claims = self.tokens.get(token)
        if claims is None or not audience or claims.get("aud") != audience:
            raise InvalidMachineTokenError
        return claims


@pytest.fixture
def gateway() -> _StubMachineTokenGateway:
    return _StubMachineTokenGateway()


def _machine_app(gateway: _StubMachineTokenGateway, monkeypatch: pytest.MonkeyPatch, audience: str) -> FastAPI:
    from presentation.fastapi.app import create_app

    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    register_issuer(_ISSUER)
    monkeypatch.setenv("MACHINE_AUDIENCE", audience)
    monkeypatch.setenv("MACHINE_CLIENTS", json.dumps(_CLIENTS))
    app = create_app()
    app.dependency_overrides[machine_token_gateway] = lambda: gateway
    return app


@pytest.fixture
def machine(
    engine: sa.Engine, gateway: _StubMachineTokenGateway, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    with TestClient(_machine_app(gateway, monkeypatch, _AUDIENCE)) as client:
        yield client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _exchange(client: TestClient, token: str) -> dict[str, Any]:
    response = client.post("/api/machine/token", headers=_bearer(token))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _audit(engine: sa.Engine, event: AuditEventType) -> list[tuple[str | None, str | None]]:
    with Session(engine) as session:
        rows = session.scalars(sa.select(AuditLogModel).where(AuditLogModel.event_type == event.value))
        return [(row.target_id, row.reason) for row in rows]


def test_listed_operations_pass_with_the_machine_token(
    machine: TestClient, gateway: _StubMachineTokenGateway, engine: sa.Engine
) -> None:
    """AC1: 許可簿に書いた操作は通る。"""
    issued = _exchange(machine, gateway.issue("robot"))
    assert issued["scopes"] == ["item:view"]
    assert issued["acts_as"] == master_data.DEFAULT_ADMIN_EMAIL
    assert "refresh_token" not in issued

    assert machine.get("/api/items", headers=_bearer(issued["access_token"])).status_code == 200
    assert _audit(engine, AuditEventType.MACHINE_TOKEN_ISSUED) == [("robot", "client=Robot")]


def test_unlisted_operations_are_refused_even_if_the_role_allows_them(
    machine: TestClient, gateway: _StubMachineTokenGateway, engine: sa.Engine
) -> None:
    """AC2・AC5: 利用者のロールでは許される操作でも、許可簿に無ければ 403。理由つきで監査に残る。"""
    token = _exchange(machine, gateway.issue("robot"))["access_token"]

    response = machine.post("/api/items", json={"name": "x"}, headers=_bearer(token))
    assert response.status_code == 403, response.text
    assert _audit(engine, AuditEventType.MACHINE_OPERATION_REFUSED) == [("robot", "not_in_allowlist: item:manage")]


def test_an_empty_allowlist_allows_nothing(machine: TestClient, gateway: _StubMachineTokenGateway) -> None:
    """AC3: 許可簿が空の機械は、どの操作も 403。"""
    issued = _exchange(machine, gateway.issue("idle"))
    assert issued["scopes"] == []
    assert machine.get("/api/items", headers=_bearer(issued["access_token"])).status_code == 403


def test_people_are_not_affected_by_the_allowlist(machine: TestClient) -> None:
    """AC4: 人のログインは許可簿の有無で変わらない。"""
    headers = sign_in(machine, master_data.DEFAULT_ADMIN_EMAIL, master_data.DEFAULT_ADMIN_PASSWORD)
    assert machine.post("/api/items", json={"name": "by a person"}, headers=headers).status_code == 201


def test_unscoped_paths_refuse_machines(
    machine: TestClient, gateway: _StubMachineTokenGateway, engine: sa.Engine
) -> None:
    """scope で守られていない口（本人の情報・ロールの切り替え）は、機械には開けない。"""
    token = _exchange(machine, gateway.issue("robot"))["access_token"]

    me = machine.get("/api/auth/me", headers=_bearer(token))
    assert (me.status_code, me.json()["detail"]["error"]) == (403, "machine_not_allowed")
    switch = machine.post("/api/auth/switch-role", json={"role": None}, headers=_bearer(token))
    assert switch.status_code == 403
    assert ("robot", "person_only: GET /api/auth/me") in _audit(engine, AuditEventType.MACHINE_OPERATION_REFUSED)


@pytest.mark.parametrize(
    ("client_id", "overrides"),
    [
        # #718 AC2: 別のアプリ宛てのトークン
        ("robot", {"aud": "api://blobshare"}),
        # #718 AC3: 人のログイン用トークン（sub_type が client でない）
        ("robot", {"sub_type": None}),
        # 主体が名乗りと違う
        ("robot", {"sub": "someone-else"}),
        # 許可簿に無い機械・振る舞う相手が居ない機械
        ("stranger", {}),
        ("ghost", {}),
        # 登録の無い発行者
        ("robot", {"iss": "https://idp.example.test/other"}),
    ],
)
def test_tokens_that_do_not_fit_are_refused_without_saying_why(
    machine: TestClient, gateway: _StubMachineTokenGateway, client_id: str, overrides: dict[str, Any]
) -> None:
    response = machine.post("/api/machine/token", headers=_bearer(gateway.issue(client_id, **overrides)))
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["error"] == "machine_authentication_required"
    assert "set-cookie" not in response.headers


def test_refusals_are_audited_with_the_client(
    machine: TestClient, gateway: _StubMachineTokenGateway, engine: sa.Engine
) -> None:
    """AC5: 換えるところで断ったものも、名乗った機械と理由つきで残る。"""
    machine.post("/api/machine/token", headers=_bearer(gateway.issue("stranger")))
    assert _audit(engine, AuditEventType.MACHINE_TOKEN_REFUSED) == [("stranger", "machine_client_not_registered")]


def test_an_empty_audience_closes_the_entrance(
    engine: sa.Engine,
    gateway: _StubMachineTokenGateway,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#718 AC1: 宛名が空なら、正しいトークンでも 401。起動のログにも出る。"""
    with caplog.at_level(logging.ERROR), TestClient(_machine_app(gateway, monkeypatch, "")) as client:
        response = client.post("/api/machine/token", headers=_bearer(gateway.issue("robot")))
    assert response.status_code == 401
    assert "machine_entrance_closed_audience_missing" in caplog.messages
