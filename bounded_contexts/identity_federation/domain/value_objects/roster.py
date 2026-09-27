"""assay が答える「いま誰がこのアプリを使ってよいか」（ADR-0043）。

idp の ADR-0057 の口が返す形をそのまま写した値。載っているのは ``sub`` と状態だけで、
プロフィールは含まない（属性の写しはログインのたびに渡っている。ADR-0042）。

⚠ **知らない状態は「触らない」へ倒す。** assay が 4 つ目の状態を足した日に、こちらが
「知らない＝止める」と読むと**全員が止まる**。読めない値で人を止めない。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RosterState(Enum):
    """名簿に載る 1 人の扱い。**RP が取る行動**で 3 つに分かれる（idp の ADR-0057）。"""

    #: いま使ってよい。
    ALLOWED = "allowed"
    #: assay に居るが、いまは使えない。⚠ **結び付きは残す**（向こうで戻れば、そのまま SSO で入れる）。
    BLOCKED = "blocked"
    #: assay のこのテナントに居ない（＝消えた）。結び付きごと落としてよい。
    UNKNOWN = "unknown"
    #: ⚠ assay が**こちらの知らない値**を返した・名簿に載っていない。何もしない。
    UNRECOGNISED = ""

    @classmethod
    def of(cls, value: str) -> RosterState:
        for state in cls:
            if state is not cls.UNRECOGNISED and state.value == value:
                return state
        return cls.UNRECOGNISED

    @property
    def ends_sessions(self) -> bool:
        """この状態は「もう SSO のセッションを使わせない」か。"""
        return self in {RosterState.BLOCKED, RosterState.UNKNOWN}

    @property
    def drops_the_link(self) -> bool:
        """結び付き（``federated_identities`` の行）まで落としてよいか。

        ⚠ **止まっただけの人の結び付きは落とさない。** 落とすと、向こうで戻ったときに
        本人がもう一度結び付け直すことになる（ADR-0040 により本人の操作でしか作れない）。
        """
        return self is RosterState.UNKNOWN


@dataclass(frozen=True)
class RosterEntry:
    """名簿の 1 行。"""

    subject: str
    state: RosterState

    @classmethod
    def of(cls, payload: dict[str, object]) -> RosterEntry | None:
        """応答の 1 要素から組み立てる。``sub`` が読めなければ ``None``。"""
        subject = payload.get("sub")
        state = payload.get("state")
        if not isinstance(subject, str) or not subject:
            return None
        return cls(subject=subject, state=RosterState.of(state if isinstance(state, str) else ""))


@dataclass(frozen=True)
class Roster:
    """1 回の問い合わせで受け取った名簿。

    ⚠ **「引けなかった」をこの型で表さない。** 引けなかったときは例外で止め、照合そのものを
    見送る ——空の名簿と区別が付かなくなると、assay が不調なだけで全員を止める（ADR-0043）。
    """

    entries: tuple[RosterEntry, ...]

    def state_of(self, subject: str) -> RosterState:
        """その ``sub`` の状態。⚠ **名簿に無い `sub` は `UNRECOGNISED`**（＝触らない）。"""
        for entry in self.entries:
            if entry.subject == subject:
                return entry.state
        return RosterState.UNRECOGNISED


__all__ = ["Roster", "RosterEntry", "RosterState"]
