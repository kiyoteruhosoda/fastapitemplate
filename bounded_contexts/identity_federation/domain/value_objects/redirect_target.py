"""ログイン後に戻す画面（SPA の経路）。

**外部の URL へは戻さない。** ``?redirect_to=`` は攻撃者が自由に付けられる
パラメータで、そのまま使うとログインの直後に別のサイトへ飛ばせてしまう
（オープンリダイレクト）。受け付けるのは自サイト内の絶対パスだけとし、外れた
ものは黙って既定の入口へ倒す。
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TARGET = "/"


@dataclass(frozen=True)
class RedirectTarget:
    path: str = DEFAULT_TARGET

    @classmethod
    def parse(cls, value: str | None) -> RedirectTarget:
        """安全な経路だけを通す。判断できないものは既定の入口。

        ``//example.com`` は「スキーム相対の URL」で外部へ出るため弾く。
        ``\\`` は一部のブラウザが ``/`` として扱うため同じく弾く。
        """
        candidate = (value or "").strip()
        if not candidate.startswith(DEFAULT_TARGET):
            return cls()
        if candidate.startswith(("//", "/\\")):
            return cls()
        return cls(candidate)


__all__ = ["DEFAULT_TARGET", "RedirectTarget"]
