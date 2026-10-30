"""メモを扱う人（ADR-0070）。

``user_id`` はトークンから、``group_ids`` は**その場で DB から**取る。所属はトークンに
載せない ——グループは資源の数だけ増え、載せるとトークンが膨らむ（Azure がグループの
クレームを 200 件で打ち切るのと同じ問題）。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Viewer:
    user_id: int
    #: 本人が入っているグループ（自分のテナントの中だけ）
    group_ids: frozenset[int]

    def can_share_with(self, group_id: int | None) -> bool:
        """共有先に選べるか。共有しない（``None``）か、自分が入っているグループだけ。"""
        return group_id is None or group_id in self.group_ids


@dataclass(frozen=True)
class ShareTarget:
    """共有先に選べるグループ。"""

    group_id: int
    name: str
