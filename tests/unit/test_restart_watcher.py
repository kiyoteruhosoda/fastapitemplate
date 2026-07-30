"""再起動ウォッチャーの判定（DB もスレッドも使わない）。"""

from __future__ import annotations

from datetime import UTC, datetime

from shared.kernel.restart import RestartRequest, RestartScope, RestartWatcher


class _StubStore:
    def __init__(self, request: RestartRequest | None = None) -> None:
        self.request = request

    def load(self, scope: RestartScope) -> RestartRequest | None:
        return self.request


class _RecordingTerminator:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    def terminate(self, reason: str) -> None:
        self.reasons.append(reason)


def _request(token: str) -> RestartRequest:
    return RestartRequest(
        scope=RestartScope.WEB,
        token=token,
        requested_at=datetime(2026, 7, 29, tzinfo=UTC),
        requested_by="user:1",
        reason=None,
    )


def _watcher(store: _StubStore, terminator: _RecordingTerminator) -> RestartWatcher:
    watcher = RestartWatcher(RestartScope.WEB, store=store, terminator=terminator)
    # start() はスレッドを起こすため、基準値の確定だけを同じ手順で再現する
    watcher._baseline_token = store.request.token if store.request else None
    return watcher


def test_no_request_means_no_restart() -> None:
    terminator = _RecordingTerminator()
    watcher = _watcher(_StubStore(None), terminator)
    assert watcher.check_once() is False
    assert terminator.reasons == []


def test_the_request_seen_at_startup_does_not_trigger_a_restart() -> None:
    # 起動時にすでに存在した要求で再起動すると、起動のたびに落ち続ける
    store = _StubStore(_request("token-1"))
    terminator = _RecordingTerminator()
    watcher = _watcher(store, terminator)
    assert watcher.check_once() is False
    assert terminator.reasons == []


def test_a_new_token_triggers_a_restart() -> None:
    store = _StubStore(_request("token-1"))
    terminator = _RecordingTerminator()
    watcher = _watcher(store, terminator)

    store.request = _request("token-2")
    assert watcher.check_once() is True
    assert "scope=web" in terminator.reasons[0]
    assert "requested_by=user:1" in terminator.reasons[0]


def test_the_same_request_is_not_acted_on_twice() -> None:
    store = _StubStore(_request("token-1"))
    terminator = _RecordingTerminator()
    watcher = _watcher(store, terminator)

    store.request = _request("token-2")
    assert watcher.check_once() is True
    assert watcher.check_once() is False
    assert len(terminator.reasons) == 1
