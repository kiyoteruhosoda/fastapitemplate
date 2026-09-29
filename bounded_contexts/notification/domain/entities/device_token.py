from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceToken:
    """スマホアプリ 1 台の通知の宛先（FCM の登録トークン。ADR-0049）。

    トークンは FCM がアプリの入った端末ごとに発行し、アプリを入れ直す・データを消すと
    変わる。これが端末の識別になる（Web Push の ``endpoint`` と同じ役）。
    """

    user_id: int
    token: str
    #: いまは ``android`` だけ。iOS を足すときに分けられるよう持っておく。
    platform: str = "android"
