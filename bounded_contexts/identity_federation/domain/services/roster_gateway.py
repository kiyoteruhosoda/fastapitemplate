"""assay の名簿を引く窓口（ADR-0043。実装は Infrastructure 層）。

⚠ **引けなかったことを「空」で表さない。** 実装は失敗を
:class:`~bounded_contexts.identity_federation.domain.exceptions.IdentityProviderUnavailableError`
で知らせ、呼び出し側は照合そのものを見送る ——空と区別が付かないと、assay が不調なだけで
全員を止めることになる。

⚠ **このサービスアカウントがまだアプリの名乗りとして結び付いていない**ときは
:class:`~bounded_contexts.identity_federation.domain.exceptions.MachineNotBoundToApplicationError`
で分けて知らせる（障害ではなく準備待ち）。こちらも何も変えない。
"""

from __future__ import annotations

from typing import Protocol

from bounded_contexts.identity_federation.domain.value_objects.roster import Roster


class RosterGateway(Protocol):
    def fetch(self, *, subjects: tuple[str, ...]) -> Roster:
        """*subjects* それぞれの消息を引く（どのアプリの名簿かは、名乗ったサービスアカウントから assay が決める）。

        ⚠ **名指しで聞く。** ``unknown``（＝向こうに居ない）が返るのはこの形だけで、
        候補の一覧を引いても「消えた」は分からない。
        """


__all__ = ["RosterGateway"]
