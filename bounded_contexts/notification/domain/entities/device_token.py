from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceToken:
    """Notification target for one installed mobile app (an FCM registration token; ADR-0081 §5).

    FCM issues the token per device the app is installed on; it changes when the app is
    reinstalled or its data is cleared. It identifies the device (same role as Web Push's ``endpoint``).
    """

    user_id: int
    token: str
    #: Only ``android`` for now. Kept so iOS can be told apart when it is added.
    platform: str = "android"
