"""IdP 側のログインセッション 1 つ分の宛名（ADR-0036）。

``(issuer, subject)`` は「誰か」で、``session_id``（ID トークンの ``sid``）は
「どのログインか」。停止の伝播はこの 3 つ組を宛名にして届く ——``sid`` まで
分かっていれば**その端末のセッションだけ**を落とせる。

``session_id`` が ``None`` になるのは 2 通りある。

- **IdP が ``sid`` を出さない。** この場合は利用者単位でしか失効できない。
- **停止の通知に ``sid`` が無い**（利用者ごと止めた）。このときは
  その利用者のセッションを**すべて**落とす。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FederatedSession:
    issuer: str
    subject: str
    session_id: str | None = None


__all__ = ["FederatedSession"]
