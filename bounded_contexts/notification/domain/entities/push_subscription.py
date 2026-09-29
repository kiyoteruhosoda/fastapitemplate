from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PushSubscription:
    """端末（ブラウザ）1 つの Web Push の購読。

    ``endpoint`` は通知サービスが端末ごとに発行する URL で、これが端末の識別になる。
    ``p256dh`` / ``auth`` は本文を暗号化する鍵（端末が作り、通知サービスは中身を読めない）。
    """

    user_id: int
    endpoint: str
    p256dh: str
    auth: str
