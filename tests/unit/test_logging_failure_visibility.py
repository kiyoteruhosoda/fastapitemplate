"""ログ基盤そのものが失敗したときに、それが見えること。

ログを書く側が例外を握り潰すと、症状は「管理画面にログが出ない」「保存した設定
が効かない」だけになり、原因（DB 未接続・マイグレーション前・列の不一致）が
どこにも残らない。**処理は止めない／黙りもしない**の両立をここで確かめる。
"""

from __future__ import annotations

import logging

import pytest

from shared.kernel.logging.db_log_handler import DbLogHandler
from shared.kernel.settings.settings import ApplicationSettings


def _record() -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)


def test_write_failure_does_not_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """本処理はログのために落とさない。"""
    handler = DbLogHandler()
    monkeypatch.setattr(handler, "handleError", _ignore)
    monkeypatch.setattr(
        "shared.kernel.logging.db_log_handler.write_log_rows",
        _raise,
    )

    handler.emit(_record())  # 例外が漏れない


def test_write_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """失敗は ``handleError``（stderr）で知らせる。黙って捨てない。"""
    handler = DbLogHandler()
    reported: list[logging.LogRecord] = []
    monkeypatch.setattr(handler, "handleError", reported.append)
    monkeypatch.setattr(
        "shared.kernel.logging.db_log_handler.write_log_rows",
        _raise,
    )

    record = _record()
    handler.emit(record)

    assert reported == [record]


def _raise(rows: object) -> None:
    raise RuntimeError("database is locked")


def _ignore(record: logging.LogRecord) -> None:
    """``handleError`` の差し替え（テスト中に stderr を汚さない）。"""


def test_unreadable_system_settings_are_reported_once(caplog: pytest.LogCaptureFixture) -> None:
    """DB から設定を読めない状態は 1 度だけ警告する（TTL ごとに出すと溢れる）。"""
    settings = ApplicationSettings(env={})

    with caplog.at_level(logging.DEBUG, logger="shared.kernel.settings.settings"):
        # エンジン未設定 = 読めない。TTL を潰して 2 回読ませる
        assert settings.log_level == "INFO"
        settings.reload_db_overrides()
        assert settings.log_level == "INFO"

    messages = [record.message for record in caplog.records]
    assert messages.count("system_settings_unreadable") == 1
