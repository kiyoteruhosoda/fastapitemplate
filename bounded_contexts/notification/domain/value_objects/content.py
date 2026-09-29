"""お知らせの中身（題・本文・押したときの行き先）。"""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.notification.domain.exceptions import NotificationValidationError

TITLE_MAX_LENGTH = 200
BODY_MAX_LENGTH = 2000
LINK_MAX_LENGTH = 1000


def _validated_link(link_url: str | None) -> str | None:
    """行き先は ``https://`` / ``http://`` の絶対 URL か、このアプリの中のパス（``/items``）。

    ⚠ ``javascript:`` などを通すと、押した人の画面で任意のスクリプトが走る。
    ``//evil.example`` はパスに見えて別のホストへ飛ぶので断る。
    """
    if link_url is None or not link_url.strip():
        return None
    link = link_url.strip()
    if len(link) > LINK_MAX_LENGTH:
        raise NotificationValidationError("link_too_long")
    if link.startswith("/") and not link.startswith(("//", "/\\")):
        return link
    if link.startswith(("https://", "http://")):
        return link
    raise NotificationValidationError("link_not_allowed")


@dataclass(frozen=True)
class NotificationContent:
    title: str
    body: str
    link_url: str | None

    def __post_init__(self) -> None:
        if not self.title or self.title != self.title.strip():
            raise NotificationValidationError("title_required")
        if len(self.title) > TITLE_MAX_LENGTH:
            raise NotificationValidationError("title_too_long")
        if len(self.body) > BODY_MAX_LENGTH:
            raise NotificationValidationError("body_too_long")

    @classmethod
    def of(cls, title: str, body: str, link_url: str | None) -> NotificationContent:
        """管理者が書いた内容から作る（前後の空白を落とし、行き先を検証する）。"""
        return cls(title=title.strip(), body=body.strip(), link_url=_validated_link(link_url))
