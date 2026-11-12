"""Notification content (title, body, and where tapping it leads)."""

from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.notification.domain.exceptions import NotificationValidationError

TITLE_MAX_LENGTH = 200
BODY_MAX_LENGTH = 2000
LINK_MAX_LENGTH = 1000


def _validated_link(link_url: str | None) -> str | None:
    """The link is an absolute ``https://`` / ``http://`` URL or a path within this app (``/items``).

    ⚠ Letting ``javascript:`` and the like through would run arbitrary script on the screen of whoever taps it.
    ``//evil.example`` looks like a path but goes to another host, so it is refused.
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
        """Build from what an admin wrote (trim surrounding whitespace and validate the link)."""
        return cls(title=title.strip(), body=body.strip(), link_url=_validated_link(link_url))
