# CLAUDE.md

このプロジェクト固有の設計ルール・制約事項をまとめる。

## ドキュメント運用

進捗・変更・設計判断は `docs/` 配下で管理する。

```
docs/
├── ARCHITECTURE.md    # 設計・レイヤー構成・命名規則（DDDの実装パターン解説）
├── ER.md              # ER図・テーブル定義（DB スキーマを変えたら更新）
├── OPERATIONS.md      # 手順書（下記「ドキュメントの役割分担」参照）
├── Progress.md        # 進行中・未着手タスクのみ
├── CHANGELOG.md       # 完了した重要な変更の要約
├── decisions/         # 設計判断（ADR-NNNN-*.md、雛形は ADR-template.md）
└── history/           # 後から経緯を追いたい規模の変更記録

frontend/README.md     # 画面遷移図・画面仕様・操作マニュアル（画面を変えたら更新）
```

運用ルール:

1. **開発開始時** → `docs/Progress.md` に TODO を追加する。
2. **作業中** → `docs/Progress.md` を更新する（状態・メモ）。
3. **完了時** → `docs/Progress.md` から削除し、重要なら `docs/CHANGELOG.md`（要約）／
   `docs/history/`（経緯）へ移す。Progress には完了項目を残さない。
4. **重要な変更だけ** `docs/history/` に記録する（細かな進捗は残さない）。
5. **設計判断は ADR** として `docs/decisions/ADR-NNNN-*.md` に残す。
6. **画面を変えたら `frontend/README.md`**、**DB スキーマを変えたら `docs/ER.md`** を
   同じコミットで更新する（下記「変更したら必ず更新するドキュメント」）。

### タスク管理（`docs/Progress.md`）— 必須

`docs/Progress.md` は**唯一のタスク一覧**として扱う。実装を始める前に必ず開き、
終わったら必ず閉じる。守ること:

- **着手前に行を追加する。** 番号（`T<n>`、既存と重複しない連番）・概要・状態・
  影響度・工数を埋める。指示された作業がそのまま 1 行になる。
- **状態を進める。** ⬜未着手 → 🚧進行中 → （完了なら行を削除）。判断を仰ぐ必要が
  出たら 🟡要判断 にして、理由と選択肢を「詳細」に書く。
- **完了した行は残さない。** 削除し、重要なら `docs/CHANGELOG.md`（要約）／
  `docs/history/`（経緯）へ移す。「✅完了」の状態は使わない。
- **完了報告の前に更新する。** Progress の更新はタスクの一部であり、後回しにしない。
- 一時的なメモ・思いつきをここに溜めない。着手予定のあるものだけを載せる。

`docs/Progress.md` は**優先順・番号・概要・状態・影響度・工数の表**で書く。
補足が必要なものだけ表の下に「詳細」として番号付きで記載する。

```
| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T1 | 〇〇を実装 | 🚧進行中 | 中 | 大 |
```

- 状態: ⬜未着手 / 🚧進行中 / 🟡要判断
- 影響度・工数: 大 / 中 / 小

### 設計判断（`docs/decisions/` の ADR）— 必須

**選択肢があり、後から「なぜこうなっているのか」を聞かれる決定は、必ず ADR として
`docs/decisions/ADR-NNNN-<slug>.md` に残す。** コード中のコメントやコミットメッセージ、
`docs/history/` で代替しない。

ADR を書く対象の例:

- 技術・ライブラリ・ミドルウェアの選定と、採らなかった選択肢
- レイヤー構成・コンテキスト分割・依存方向に関する決定
- DB スキーマの方針（ネイティブ ENUM を使わない、テーブルを分ける等）
- 認証・認可の方式、運用方式（品質ゲート・デプロイ手順）の決定
- 過去の ADR を覆す決定（新しい ADR を追加し、古い方の「状態」に置き換えを明記する）

書き方:

- 雛形 `docs/decisions/ADR-template.md` をコピーする。見出し構成
  （文脈 → 決定 → 理由 → 影響）を変えない。
- `NNNN` は既存の最大値 + 1 のゼロ埋め 4 桁。**採番の重複と欠番を作らない。**
- 状態は 提案 / 承認 / 廃止（`ADR-NNNN` で置き換え）のいずれか。
  一度承認した ADR は書き換えず、**新しい ADR で置き換える**（古い方の状態を更新する）。
- 実装より先に、または実装と同じコミットで追加する。後追いで書き足さない。
- 関連するコード・ドキュメントからは ADR 番号でリンクする（決定の重複記述をしない）。

### 変更したら必ず更新するドキュメント

コードとドキュメントの乖離を防ぐため、**変更と同じコミットで**対応するドキュメントを
更新する。「あとで直す」を残さない。

| 変更した内容 | 更新するドキュメント |
|---|---|
| 画面の追加・削除、ルート（URL）の変更、画面遷移、必要 scope、画面上の操作手順 | `frontend/README.md`（画面遷移図・画面一覧・画面仕様・操作マニュアルの 4 か所） |
| テーブル・カラム・リレーション・制約の変更（モデル + マイグレーション） | `docs/ER.md`（ER 図・テーブル定義） |
| 操作手順・コマンドの変更 | `docs/OPERATIONS.md` |
| レイヤー構成・命名規則・DDD パターンの変更 | `docs/ARCHITECTURE.md` |
| 設定キーの追加・変更 | 下記「設定管理」の 3 ファイル |
| 設計判断を伴う変更 | `docs/decisions/ADR-NNNN-*.md`（上記） |
| 進行中タスクの状態 | `docs/Progress.md`（上記） |

`frontend/README.md` の画面遷移図と `docs/ER.md` の ER 図は **Mermaid** で書く
（GitHub でそのまま描画される）。図を消してテキストだけにしない。

### ドキュメントの役割分担（何をどこに書くか）

| ドキュメント | 役割 | 書くこと | 書かないこと |
|---|---|---|---|
| `docs/OPERATIONS.md` | 手順書 | 「〇〇したいとき、〇〇する」という操作手順・コマンドのみ | なぜそうなっているか、過去に何が起きたか、内部の仕組み、API仕様 |
| `docs/ARCHITECTURE.md` | 設計ガイド | レイヤー構成・命名規則・DDDパターンの解説 | 個別機能の操作手順、環境変数の一覧（OPERATIONS.md へ） |
| `docs/ER.md` | データモデル仕様 | ER 図・テーブルとカラムの意味・モデリング規約 | 個別機能の操作手順、SQL の実行手順（OPERATIONS.md へ）、過去のスキーマの経緯（CHANGELOG.md へ） |
| `frontend/README.md` | 画面仕様・操作マニュアル | 画面遷移図・画面ごとの目的と操作・必要 scope・利用者向けの操作手順 | API のリクエスト／レスポンス仕様（Swagger が正本）、過去の画面の経緯 |
| `scripts/README.md`（および各コンテキストの README） | 仕様書 | スクリプト・設定が**現在どう動くか**（現状の挙動・制約・注意点） | 「以前は〜だったが」「原因は〜だった」という過去の不具合の経緯 |
| `docs/CHANGELOG.md` | 変更履歴 | 過去の不具合とその原因・修正内容 | — |

迷ったら「これは手順か（OPERATIONS）」「設計の解説か（ARCHITECTURE）」
「データ構造か（ER）」「画面か（frontend/README）」「現在の仕様か（README）」
「過去の経緯か（CHANGELOG）」で判断する。
同じ内容を複数箇所に重複して書かない。

**APIエンドポイント仕様は手書きしない。** FastAPI が自動生成する
Swagger UI（`/docs`）・`/openapi.json` が唯一の出所。
ドキュメントにはそこへのリンクだけを書く。

---

## 設計方針

- **DDD（ドメイン駆動設計）** を採用する。Presentation / Application / Domain / Infrastructure の4層構造。依存方向は Presentation → Application → Domain、Infrastructure は Domain のインターフェースを実装する。
- **SOLID 原則**を遵守する。特に SRP（単一責務）と DIP（依存性逆転）を重視。
- **依存注入**を使う。`new` の直接使用より Factory / コンストラクタインジェクション（FastAPI では `Depends()`）を優先。
- `util` / `helper` といった曖昧な名前のクラス・モジュールを作らない。
- 命名はドメイン語彙（ユビキタス言語）を使う。技術用語・略語で上書きしない。

---

## 環境要件

| 項目 | バージョン |
|---|---|
| Python | 3.12 以上（`python:3.12-slim` ベース） |
| 依存管理 | uv（`uv sync` / `uv run`） |
| DB（本番） | MariaDB 10.11.x |
| DB（開発・テスト） | SQLite（`with_variant` で両立。ADR-0001 参照） |
| SQLAlchemy | 2.x（Declarative Base 構文） |
| Alembic | migrations/ 配下で管理 |
| ASGI | Uvicorn（本番は Gunicorn + UvicornWorker、`--workers=2` 推奨） |
| Node.js | 24.x LTS（フロントエンドビルド用） |
| ホスト | Linux（Docker 上。Synology DSM 7.x 等） |

---

## ディレクトリ構成

```
bounded_contexts/<context>/
  domain/           # ビジネスロジック（フレームワーク・DB依存なし）
  application/      # ユースケース・トランザクション境界
  infrastructure/   # DB・外部API実装
  presentation/     # Router・Schema（そのコンテキスト固有のAPI）

shared/
  domain/auth/      # ユーザー・ロール・権限のマスタデータ（master_data.py）
  infrastructure/models/  # 共有 SQLAlchemy モデル
  kernel/
    settings/       # settings.py, system_settings_defaults.py
    logging/        # 構造化ログ
    database/       # db.py / session.py (SQLAlchemy)

presentation/fastapi/
  app.py            # FastAPI アプリケーションファクトリ
  routers/          # 共通・管理API（admin/ 配下に管理系）
  schemas/          # Pydantic スキーマ（presentation/fastapi 全域で共有）
  dependencies/     # Depends() 用依存関数（auth, database）
  middleware/       # リクエストログ等
  services/         # Presentation 層サービス（トークン発行等）
  admin/            # 管理画面向け定義（system_settings_definitions.py）

frontend/           # React + TypeScript + Vite（SPA スケルトン）
```

新しい機能は `bounded_contexts/<context>/` として追加する。
`bounded_contexts/example/` が最小構成の見本（Item の CRUD）。

---

## 権限管理

- 認可は **ロールではなく scope（権限コード値）** で行う。ロール名での分岐禁止。
- 有効な scope = ユーザーの全ロールが持つ権限の和集合。
- 各エンドポイントに `Depends(require_permission("scope_name"))` を付ける
  （`presentation/fastapi/dependencies/auth.py`）。
- 権限の検証は依存関数で行い、ルーター本体には検証済みの
  `AuthenticatedPrincipal` のみ渡す。
- JWT 発行時の scope はユーザーの保有権限の範囲内で指定。未指定・空 = 権限なし。

---

## DDL 管理

- テーブル変更は必ず **Alembic マイグレーションスクリプト** で行う。`ALTER TABLE` / `CREATE TABLE` を直接実行しない。
- マイグレーションファイルは `migrations/versions/<revision_id>_<description>.py`。
- 各ファイルの先頭に `from __future__ import annotations` を必ず記述。
- `upgrade()` / `downgrade()` の両方を実装する。
- ベースラインは `migrations/versions/0001_init_master.py`（全テーブルを現行モデルから生成）。
- マスタデータ（ロール・権限・初期管理者）は `shared/domain/auth/master_data.py` を唯一の出所とし、`versions/*_seed_master_data.py` と `scripts/seed_master_data.py` の双方が参照する。値をどちらかに直書きしない。
- テーブル・カラム・リレーション・制約を変更したら **`docs/ER.md` の ER 図とテーブル定義を同じコミットで更新する**。

---

## DB モデリング（SQLAlchemy）

- **DB ネイティブ ENUM カラムを使わない。** MariaDB の `ENUM` は値追加に `ALTER TABLE` が必要で DDL 運用と噛み合わず、序数変更でデータが壊れる。SQLAlchemy の `Enum(...)` を使う場合は必ず **`native_enum=False`**（全バックエンドで CHECK 制約付き VARCHAR になる）を指定する。あるいは `String` + 許可値の定数管理とする。
- 型安全のための Python 側の許可値集中管理（`enum.Enum` クラスや定数タプル）は推奨。禁止しているのは「DB 側のネイティブ ENUM 型」であって、Python の列挙そのものではない。
- 主キー等の `BigInteger` は SQLite テストとの両立のため `sa.BigInteger().with_variant(sa.Integer(), "sqlite")` を使う。
- モデルを変更したら必ず対応するマイグレーションを追加する。乖離は `tests/integration/test_migration_model_consistency.py` が検出する。
- モデルを変更したら `docs/ER.md` も更新する（ER 図はコードの正本ではなく、コードに追従させる）。

---

## 設定管理（Settings）

設定値の取得は **必ず `settings` オブジェクトの `@property` 経由**。直接アクセス禁止。

```python
# OK
from shared.kernel.settings.settings import settings
value = settings.some_property

# NG
os.getenv("SOME_KEY")
SystemSetting.query.get("some_key")
```

優先順位: 環境変数 > DB（system_settings テーブル）> デフォルト値

新しい設定キーを追加する場合は以下の3ファイルすべてを更新する:

1. `shared/kernel/settings/system_settings_defaults.py` — デフォルト値
2. `shared/kernel/settings/settings.py` — `@property` の追加
3. `presentation/fastapi/admin/system_settings_definitions.py` — 管理画面項目

---

## API 設計（FastAPI + Pydantic）

- エンドポイントは FastAPI の `APIRouter` として実装。
- リクエスト・レスポンスは Pydantic `BaseModel` で定義し、Application 層には **バリデーション済みの値** のみを渡す。
- Schema から直接 Domain モデルを生成しない（Application 層で変換）。

**Schema 命名規則**: `〇〇Request` / `〇〇Response`

**配置先**:
- `presentation/fastapi` 全体で使う共通スキーマ → `presentation/fastapi/schemas/`
- 特定コンテキスト固有のスキーマ → `bounded_contexts/<context>/presentation/`

`response_model` を指定すると OpenAPI 仕様が自動生成される。

---

## 国際化（i18n）

- 翻訳はフロントエンド側で行う。`frontend/src/i18n/` 配下の言語別 JSON で管理。
- 新規メッセージは英語キーで定義し、`ja.json` に日本語訳を手動追記。
- バックエンド API はエラーコード（`{"error": "invalid_token"}` 等）を返し、
  表示文言への変換はフロントエンドが行う。

---

## ログ

- すべてのログは **JSON 形式**で stdout に出力し、同時に DB へ書き込む。
- ログには **PII を含めない**（メールアドレス・氏名・パスワード・トークン・設定値）。

記録は 2 種類ある。使い分けと設計判断は ADR-0013。

| 出力先 | 追跡キー | 用途 | ユーザー識別子 | 閲覧 scope |
|---|---|---|---|---|
| `log` テーブル | `requestId` | アプリログ（システムが何をしたか） | `user.id_hash` のみ | `log:view` |
| `audit_log` テーブル | `requestId` | 監査ログ（誰が何をしたか） | 内部 ID（`actor_user_id`） | `audit:view` |

- **アプリログを書くのは** `shared/kernel/logging` の `DbLogHandler`（全レイヤーが
  `logging` 経由で書く横断的関心事）。`LOG_DB_MIN_LEVEL` 未満は DB へ書かない。
- **監査ログを書くのは** audit コンテキスト。ルーターが操作の直後に
  `RecordAuditEvent` を呼ぶと**控えに積まれ**、リクエストの処理が完全に終わってから
  ミドルウェアが**別トランザクションでまとめて書く**。失敗したログインのように
  リクエストがロールバックされても記録が残り、かつ SQLite で書き込みロックと
  競合しない。
- 監査ログには内部 ID のみを記録する（ハッシュではない）。監査は操作を主体へ帰属
  させる記録で、後から誰か特定できなければ目的を果たさないため。値そのもの（PII）は
  記録せず、`reason` には「変更した項目名」「失敗の分類」を入れる。
- **実行者（`actor_user_id`）を入れるのは認証済みのリクエストだけ。** 未認証で叩ける
  操作（ログイン失敗・パスワードリセット）は「誰がやったか」が分かっていないので、
  相手を `target` として記録する。持ち主を実行者に据えると本人の操作に見えてしまう。
- どちらの検索も audit コンテキストが担う（`bounded_contexts/audit/presentation/`）。

時刻は常に UTC。traceback フィールドは NULLABLE（例外時のみ記録）。

---

## テスト

```
tests/
  unit/         # 外部依存なし（Domain 中心）
  integration/  # DB・ファイルシステムを使う（SQLite in-memory）
```

テスト収集は `--import-mode=importlib`（同名ファイルの衝突回避のため `pyproject.toml` に設定済み）。

デフォルトで除外されるマーカー: `smtp`（外部リソース要）。

時刻・乱数・UUID はテスト内で固定する（`unittest.mock.patch` で差し替え）。実環境の Clock クラスは存在しない。

フロントエンドのテストは `frontend/src/**/*.test.ts(x)`（Vitest + jsdom + Testing Library）。

---

## 品質ゲート

以下の 8 つを CI の**必須**ゲートとする（ADR-0006）。落ちたらマージしない。
手元では `make check` で同じ順序・同じコマンドを流せる（`make format` で自動整形）。
CI が走るのは **PR に対してと `main` への push だけ**（ADR-0009）。PR を作る前の
ブランチ push では走らないので、その間は `make check` で確認する。

| 対象 | 順 | ゲート | コマンド |
|---|---|---|---|
| Backend | 1 | 整形 | `uv run ruff format --check .` |
| Backend | 2 | 静的解析 | `uv run ruff check .` |
| Backend | 3 | 型 | `uv run mypy`（strict。テストも対象） |
| Backend | 4 | テスト | `uv run pytest` |
| Frontend | 1 | 整形 | `npm run format:check`（Prettier） |
| Frontend | 2 | 静的解析 | `npm run lint`（ESLint） |
| Frontend | 3 | 型 | `npm run type-check`（`tsc --noEmit`） |
| Frontend | 4 | テスト | `npm run test`（Vitest） |

守るべき点:

- **型注釈を省略しない。** MyPy は `strict` かつ `disallow_untyped_defs`。テストの
  関数・フィクスチャも対象。`Any`・型引数なしのジェネリクス（`dict` / `Callable`）は不可。
- **`any` を使わない。** TypeScript も `strict` + `noUncheckedIndexedAccess` +
  `exactOptionalPropertyTypes`。
- **Promise を放置しない。** async 関数をハンドラへそのまま渡さない。捨てるなら
  `void handler(e)` と明示する（`no-floating-promises` / `no-misused-promises`）。
- **依存方向を破らない。** `tests/unit/test_layer_dependencies.py` が AST で検証する。
  Domain は Application / Infrastructure / Presentation を import できず、
  フレームワーク・DB（FastAPI / SQLAlchemy 等）にも依存できない。

設計品質の基準。**すべて機械検証する**（ADR-0012。落ちたらマージしない）:

| 項目 | 基準 | 検証 | 実測 |
|---|---|---|---|
| ネスト深度 | 最大 3 | `tests/unit/test_design_metrics.py` | — |
| 関数長 | 30 行以下 | `PLR0915`（文の数 30 以下で代替） | 行数では測らない |
| 引数数 | 3 個以下 | `PLR0913`（機械検証は 4） | `Depends()`・キーワード専用引数も数えられる |
| 分岐数 | — | `PLR0912`（8 以下） | 複雑度の内訳として補助的に見る |
| 複雑度 | 10 以下（推奨 5 以下） | `C901`（10） | 推奨値 5 はレビューで見る |
| クラス長 | 200 行以下 | `tests/unit/test_design_metrics.py` | 例外はテスト内に理由付きで置く |

閾値は `pyproject.toml`（`[tool.ruff.lint.mccabe]` / `[tool.ruff.lint.pylint]`）が正本。
**基準どおりに書けない箇所を見つけたら、まず分割する。** どうしても超える場合は
理由を添えて `# noqa` か例外リストに載せ、増えるようなら基準自体を ADR で見直す。
テストの引数は `PLR0913` の対象外（フィクスチャの注入であり設計上の引数ではない）。

---

## 動的呼び出しの制限

`getattr()` / `setattr()` / `eval()` / `exec()` / `globals()` / `locals()` による動的ディスパッチは原則禁止。標準ライブラリに対する参照（`hashlib` のアルゴリズム取得など）は例外。

メソッド名や属性名を文字列で渡して実行時に解決するパターンは避け、明示的なインターフェースを使う。
