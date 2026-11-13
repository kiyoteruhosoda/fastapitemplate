from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PushSubscription:
    """Web Push subscription of one device (browser).

    ``endpoint`` is a URL the push service issues per device; it identifies the device.
    ``p256dh`` / ``auth`` are the keys that encrypt the body (made by the device; the push service
    cannot read the content).
    """

    user_id: int
    endpoint: str
    p256dh: str
    auth: str
