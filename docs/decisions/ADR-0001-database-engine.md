# ADR-0001: DB エンジンは本番 MariaDB + 開発/テスト SQLite の二本立てとする

- 日付: 2026-07-17
- 状態: 承認

## 文脈

刷新前のテンプレートは SQLite 単独だった。参照元の photonest は MariaDB 10.11 を
本番 DB とし、SQLite をテストで併用している。テンプレートとしてどちらに
揃えるかの判断が必要だった。

## 決定

本番（docker compose）は MariaDB 10.11、ローカル開発・テストは SQLite とする。
スキーマは Alembic で一元管理し、`sa.BigInteger().with_variant(sa.Integer(), "sqlite")`
等で両バックエンドの互換を保つ。

## 理由

- photonest と同一構成にすることで、デプロイスクリプト・compose 構成・
  マイグレーション運用をそのまま流用でき、テンプレートから実プロダクトへの
  移行コストが最小になる。
- SQLite を開発・テストに残すことで `uv run pytest` が外部依存なしで動き、
  CI がシンプルに保てる。
- SQLite 単独案は compose から db サービスを消せる簡潔さがあるが、
  本番想定の RDBMS 運用（マイグレーション・バックアップ）を
  テンプレートで示せなくなるため採らなかった。

## 影響

- モデル定義は MariaDB / SQLite 両対応が必須（DB ネイティブ ENUM 禁止、
  `with_variant` の使用。CLAUDE.md「DB モデリング」参照）。
- compose に db サービスと healthcheck、デプロイに migrate モードを持つ。
