"""再起動要求の永続化。

``system_settings`` テーブルの ``app.restart_request`` レコードを唯一の出所と
して、「いつ・誰が・どのサービスの再起動を要求したか」を保持する。

管理 API のプロセスから、再起動したいプロセスへ直接シグナルを送ることはできない
（Gunicorn は複数ワーカーで動き、将来サービスを分ければ別コンテナになる）。DB に
要求を置き、各プロセスが :mod:`shared.kernel.restart.watcher` で拾って自分自身を
終了させ、Docker の restart policy で復帰する。この方式ならコンテナへ docker
socket をマウントせずに済む。

要求は**スコープごとに独立して**保持する。単一の要求で上書きすると、監視の
ポーリング間隔（既定 10 秒）の内側に 2 件の要求が入ったとき、先の要求を読む前に
後の要求で上書きされ、まだ読んでいないプロセスが自分宛の再起動を取りこぼす。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from shared.kernel.restart.scope import ALL_RESTART_SCOPES, RestartScope

logger = logging.getLogger(__name__)

RESTART_REQUEST_SETTING_KEY = "app.restart_request"


@dataclass(frozen=True)
class RestartRequest:
    """あるスコープに対する直近の再起動要求。

    ``token`` は要求を識別する文字列（要求時刻の ISO 表現）。監視側は起動時に
    読んだ token を基準値とし、値が**変わった**ときだけ再起動する。時刻の大小
    ではなく変化で判定するため、アプリコンテナと DB の時計がずれていても
    再起動ループに陥らない。
    """

    scope: RestartScope
    token: str
    requested_at: datetime | None
    requested_by: str | None
    reason: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "requested_by": self.requested_by,
            "reason": self.reason,
        }

    @classmethod
    def from_payload(cls, scope: RestartScope, payload: Any) -> RestartRequest | None:
        if not isinstance(payload, dict):
            return None
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            return None
        requested_by = payload.get("requested_by")
        reason = payload.get("reason")
        return cls(
            scope=scope,
            token=token,
            requested_at=_parse_timestamp(payload.get("requested_at")),
            requested_by=requested_by if isinstance(requested_by, str) else None,
            reason=reason if isinstance(reason, str) else None,
        )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _decode_requests(payload: Any) -> dict[RestartScope, RestartRequest]:
    """保存形式 ``{"scopes": {"web": {...}}}`` を読み解く。"""
    if not isinstance(payload, dict):
        return {}
    raw_scopes = payload.get("scopes")
    if not isinstance(raw_scopes, dict):
        return {}

    requests: dict[RestartScope, RestartRequest] = {}
    for raw_scope, raw_request in raw_scopes.items():
        scope = RestartScope.parse(raw_scope)
        if scope is None:
            continue
        request = RestartRequest.from_payload(scope, raw_request)
        if request is not None:
            requests[scope] = request
    return requests


def _encode_requests(requests: Mapping[RestartScope, RestartRequest]) -> dict[str, Any]:
    return {"scopes": {scope.value: requests[scope].to_payload() for scope in ALL_RESTART_SCOPES if scope in requests}}


class RestartRequestReader(Protocol):
    """スコープ宛の再起動要求を 1 件読み出す。

    :class:`~shared.kernel.restart.watcher.RestartWatcher` はこの口だけに依存する
    （DIP）。DB を持たないテストダブルを差し替えられる。
    """

    def load(self, scope: RestartScope) -> RestartRequest | None:
        """*scope* 宛の直近の要求を返す。無ければ ``None``。"""


class RestartRequestStore:
    """``app.restart_request`` レコードの読み書き。"""

    def load_all(self) -> dict[RestartScope, RestartRequest]:
        """スコープごとの直近の要求を返す。DB が使えないときは空。"""
        from shared.kernel.settings.system_setting_records import (
            SystemSettingRecordReader,
        )

        try:
            payload = SystemSettingRecordReader.read_json(RESTART_REQUEST_SETTING_KEY)
        except Exception:
            logger.debug("再起動要求の読み取りに失敗しました", exc_info=True)
            return {}
        return _decode_requests(payload)

    def load(self, scope: RestartScope) -> RestartRequest | None:
        """*scope* 宛の直近の要求を返す。"""
        return self.load_all().get(scope)

    def save(
        self,
        session: Session,
        scopes: Iterable[RestartScope],
        *,
        requested_by: str | None = None,
        reason: str | None = None,
        requested_at: datetime | None = None,
    ) -> tuple[RestartRequest, ...]:
        """再起動要求を保存する（リクエスト内から呼ぶ）。

        対象が空の場合は全スコープを対象とする。指定したスコープの分だけを
        書き換え、対象外のスコープに残っている要求は保持する（まだ拾われて
        いない要求を消さないため）。
        """
        from shared.infrastructure.models import SystemSetting

        targets = tuple(scope for scope in ALL_RESTART_SCOPES if scope in set(scopes))
        if not targets:
            targets = ALL_RESTART_SCOPES

        moment = requested_at or datetime.now(UTC)
        token = moment.isoformat()

        record = session.get(SystemSetting, RESTART_REQUEST_SETTING_KEY)
        requests = _decode_requests(record.setting_json if record is not None else None)
        for scope in targets:
            requests[scope] = RestartRequest(
                scope=scope,
                token=token,
                requested_at=moment,
                requested_by=requested_by,
                reason=reason,
            )

        payload = _encode_requests(requests)
        if record is None:
            session.add(SystemSetting(setting_key=RESTART_REQUEST_SETTING_KEY, setting_json=payload))
        else:
            record.setting_json = payload
        session.flush()

        logger.info(
            "再起動要求を保存しました: scopes=%s requested_by=%s",
            ",".join(scope.value for scope in targets),
            requested_by or "-",
            extra={"event": "restart.requested"},
        )
        return tuple(requests[scope] for scope in targets)


__all__ = [
    "RESTART_REQUEST_SETTING_KEY",
    "RestartRequest",
    "RestartRequestReader",
    "RestartRequestStore",
]
