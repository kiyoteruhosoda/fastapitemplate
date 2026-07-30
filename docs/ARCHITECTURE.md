# ARCHITECTURE — 設計ガイド

本テンプレートのレイヤー構成・命名規則・DDD 実装パターンを解説する。
操作手順は `OPERATIONS.md`、設定キー一覧は管理画面（Config）を参照。

## レイヤー構成（DDD 4層）

```
Presentation → Application → Domain ← Infrastructure
```

- **Domain** — ビジネスロジック。フレームワーク・DB に依存しない純粋な Python。
  エンティティ（`dataclass`）、値オブジェクト（`frozen dataclass`）、
  リポジトリインターフェース（`ABC`）、ドメイン例外。
- **Application** — ユースケース・トランザクション境界。DTO への変換もここで行う。
- **Infrastructure** — Domain のリポジトリインターフェースを SQLAlchemy 等で実装する。
- **Presentation** — FastAPI Router と Pydantic Schema。HTTP の関心事のみ。

依存方向は Presentation → Application → Domain。
Infrastructure は Domain のインターフェースを実装する（依存性逆転）。

この向きは `tests/unit/test_layer_dependencies.py` が AST で検証する。禁止するのは
**逆流**で、次の向きは import した時点でテストが落ちる。

| 層 | 依存できない先 |
|---|---|
| Domain | Application / Infrastructure / Presentation |
| Application | Infrastructure / Presentation |
| Infrastructure | Application / Presentation |

Domain がフレームワーク・DB（`fastapi` / `sqlalchemy` / `pydantic` 等）を import
することも同様に落ちる。

`Presentation → Infrastructure` は**禁止しない**。最も外側の層が具体実装を組み立てて
`Depends()` に渡すのは正しい向きで、DI の配線はどこかで行う必要がある（ADR-0006）。

## bounded_contexts と shared の使い分け

- 機能は `bounded_contexts/<context>/` として追加する。1コンテキスト = 1業務領域。
  `bounded_contexts/example/`（Item CRUD）が最小構成の見本。
- 複数コンテキストから使う横断的な要素だけを `shared/` に置く:
  - `shared/domain/auth/` — 認可マスタデータ（`master_data.py` が唯一の出所）
  - `shared/infrastructure/models/` — 共有 SQLAlchemy モデル（User / Role / Permission /
    SystemSetting / Log / PasswordResetToken）
  - `shared/kernel/` — settings / logging / database / restart / timestamps
    （技術基盤。ドメイン知識を持たない）
- `presentation/fastapi/` はコンテキスト横断の API（認証・管理系）と
  アプリケーションファクトリ（`app.py`）を持つ。

## 認証・認可の設計

- 認証は JWT（access / refresh の2トークン）。発行・検証は
  `presentation/fastapi/services/token_service.py`。
- 認可は **scope（権限コード値）** ベース。ロール名で分岐しない。
  - 有効 scope = ユーザーの全ロールが持つ権限の和集合。
  - エンドポイントでは `Depends(require_permission("user:manage"))` のように宣言する。
  - 検証済みの主体は `AuthenticatedPrincipal`（`shared/application/`）として渡る。
- ロール・権限コード・初期管理者は `shared/domain/auth/master_data.py` で一元管理し、
  マイグレーションのシードと `scripts/seed_master_data.py` が参照する。

- 第二の要素（二要素認証・パスキー）は `bounded_contexts/account_security/` が持つ
  （ADR-0003）。パスワード認証は上記のまま、ログイン時に TOTP を検証する／パスキー
  だけでトークンを発行する、という形で足している。詳細はコンテキストの README。

サービスアカウント認証・外部 IdP 連携は初期スコープに含めない（ADR-0002）。

## 自己再起動の設計

管理画面から保存した設定のうち、起動時にしか読まれないもの（ログ・CORS）は
保存だけでは反映されない。`shared/kernel/restart/` がその橋渡しをする。

- 設定定義の `restart_scopes` が「反映にどのサービスの再起動が要るか」を宣言する。
- 管理 API は要求を DB（`system_settings` の `app.restart_request`）へ書く。
- 各プロセスは起動時に `RestartWatcher` を立て、自分宛の要求の token が変わったら
  自分自身を終了させる。復帰はコンテナの restart policy に任せる。

要求を DB 経由にするのは、管理 API を処理したプロセスと再起動すべきプロセスが
別だから（Gunicorn は複数ワーカー）。判定を時刻ではなく token の変化で行うのは、
時計のずれで再起動ループに陥らないようにするため（ADR-0004）。

## 設定管理の設計

`shared/kernel/settings/settings.py` の `ApplicationSettings` が
「環境変数 > DB（system_settings テーブル）> デフォルト値」の優先順位で値を解決する。

- DB 層は TTL キャッシュ付き。管理画面からの保存時は
  `SystemSettingService` が `invalidate()` を呼び即時反映する。
- DB 未接続（マイグレーション前等）では黙って環境変数とデフォルト値のみで動く。
- `DATABASE_URI` などブートストラップに必要なキーは DB 上書きの対象外
  （解決に DB 接続が必要なキーを DB から読むと再帰するため）。

## ログの設計

- `presentation/fastapi/middleware/request_logging.py` がリクエストごとに
  `requestId` を採番し、`contextvars` 経由で全ログレコードへ伝播する。
- `shared/kernel/logging/db_log_handler.py` が JSON 構造化ログを `log` テーブルへ
  書き込む。stdout への JSON 出力と併用する。
- PII 禁止。ユーザー識別子はハッシュ（`user.id_hash`）のみ。

## フロントエンド

`frontend/` は React + TypeScript + Vite の SPA スケルトン。

- `services/api.ts` — fetch ラッパー。JWT の保持・期限切れ時の refresh・401 処理。
- `store/` — 認証状態（React Context）。
- `pages/` — 画面単位。管理画面は scope で表示制御する。
- `i18n/` — 言語別 JSON（en / ja）。キーは英語。訳の抜けは
  `tests/unit/test_i18n_dictionaries.py` が検出する。
- `theme/` — テーマ（light / dark / system）。配色は `index.css` の CSS 変数で持ち、
  `<html data-theme>` を切り替えて解決する。
- 言語・テーマの既定値と選択肢は `GET /api/ui/settings`（公開）から受け取り、
  利用者の選択は `localStorage` に持つ（ADR-0005）。
- ビルド成果物（`frontend/dist`）は FastAPI の `routers/spa.py` が配信する。
  開発時は Vite dev server（`npm run dev`）から API へプロキシする。
- テストは対象と同じ階層に `*.test.ts(x)` として置く（Vitest + jsdom +
  Testing Library）。描画が例外を投げることの検証には
  `src/test-support/renderErrors.ts` を使う。

## 命名規則

- Pydantic スキーマ: `〇〇Request` / `〇〇Response`
- リポジトリインターフェース: `I〇〇Repository`（Domain）、実装は `Sql〇〇Repository` 等
- ユースケース: 動詞句のクラス名（`CreateItem`、`ListItems`）
- 権限コード: `<資源>:<操作>`（例 `user:manage`、`admin:system-settings`）
