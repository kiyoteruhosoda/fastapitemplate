# ADR-0006: 品質は CI の必須ゲートで守る（整形・静的解析・型・テスト）

- 日付: 2026-07-30
- 状態: 承認

## 文脈

これまでの CI は Backend が `ruff check` と `pytest`、Frontend が `npm run build`
だけだった。次の穴が空いていた。

- **整形が揃わない**。`ruff format` を誰も流しておらず、162 ファイル中 100 ファイルが
  未整形だった。Frontend には整形ツール自体が無かった。
- **型が保証されない**。Python 側に型チェッカーが無く、`sessionmaker`・`dict`・
  `Callable` の型引数漏れや、`Result` に無い属性へのアクセスが放置されていた。
  Frontend も `strict` のみで、添字アクセスや任意プロパティの穴が残っていた。
- **Frontend にテストが 1 本も無かった**。`tsc && vite build` が通ることだけが基準で、
  振る舞いは誰も検証していなかった。
- **DDD の依存方向が人の目にしか頼っていない**。Domain が SQLAlchemy を import しても
  何も落ちなかった。

長期保守を前提にする以上、レビューの注意力に依存する部分を機械へ寄せる必要があった。

## 決定

Lint → Type Check → Test を CI の**必須**ゲートにする。落ちたらマージできない。

| 対象 | ゲート | コマンド |
|---|---|---|
| Backend | 整形 | `uv run ruff format --check .` |
| Backend | 静的解析 | `uv run ruff check .` |
| Backend | 型 | `uv run mypy` |
| Backend | テスト | `uv run pytest` |
| Frontend | 整形 | `npm run format:check`（Prettier） |
| Frontend | 静的解析 | `npm run lint`（ESLint） |
| Frontend | 型 | `npm run type-check`（`tsc --noEmit`） |
| Frontend | テスト | `npm run test`（Vitest） |

設定の要点:

- Ruff: `line-length = 120`、`select = [E, F, I, B, UP, SIM, C4, ARG, N, RET, PTH, RUF]`。
- MyPy: `strict = true` に加えて `warn_unreachable` / `implicit_reexport = false` まで有効。
  対象はテストを含む全ソース（`[tool.mypy] files`）。
- ESLint: `typescript-eslint` の `strictTypeChecked` を土台に、
  `no-floating-promises` / `no-explicit-any` / `consistent-type-imports` /
  `react-hooks/*` / `sonarjs/cognitive-complexity`（15）を明示的に error にする。
- TypeScript: `strict` に `noUncheckedIndexedAccess` /
  `exactOptionalPropertyTypes` / `noImplicitOverride` /
  `noFallthroughCasesInSwitch` を追加。
- DDD の依存方向は `tests/unit/test_layer_dependencies.py` が AST で検証する。

CI の各ステップは `if: always()` を付け、前段が落ちても後段を実行する。

## 理由

- **整形はツールに一本化する**。差分から「好み」を消すと、レビューが設計の話だけに
  なる。導入時に 100 ファイルが変わるが、一度で済む機械的な変更なので先に払う。
- **MyPy をテストにも掛ける**。テストの型付けを免除すると、フィクスチャの取り違えや
  シグネチャのずれが本番コードの型情報を空洞化させる。実際、テストを型付けした結果
  `RestartWatcher` が具象 `RestartRequestStore` に依存していた DIP 違反が見つかり、
  `RestartRequestReader` Protocol を切り出す修正につながった。
  型なし関数を許す設定（`disallow_untyped_defs = false` の per-module override）は
  取らない。
- **依存方向を ADR とテストの二重で持つ**。文章だけの規約は必ず腐る。AST で
  「Domain は Application / Infrastructure / Presentation を import しない」等を
  検証すれば、違反した時点で落ちる。
- **`Presentation → Infrastructure` は禁止しない**。最も外側の層が具体実装を
  組み立てて `Depends()` に渡すのは Clean Architecture でも正しい向きで、
  DI の配線はどこかで行う必要がある。現に 17 か所ある。禁止するなら
  Application 層に組み立て責務を移す別の設計判断が必要で、本 ADR の範囲外とした。
- **`if: always()`** にしたのは、1 回の CI で全部の指摘を受け取れるようにするため。
  fail-fast だと「整形を直す → 型で落ちる → また直す」で往復が増える。

検討して捨てた代替案:

- **pre-commit フックだけで済ませる**: ローカルで `--no-verify` を通されると意味が
  無い。CI を最終的な砦にし、フックは任意の補助とする（`make format` を用意）。
- **`import-linter` で依存方向を検査する**: 依存が 1 つ増える。検査したい規則は
  「層 → 層」の数本だけで、AST で 150 行に収まるため自前のテストにした。

## 影響

- 既存コードへの一括修正が入った。Ruff Format で 100 ファイル、
  MyPy strict 対応で 114 件、ESLint / `tsc` で 74 件を直した。
- 新規コードは 8 ゲートすべてを通す必要がある。ローカルでは `make check` で
  同じ順序・同じコマンドを流せる。
- Ruff の `RUF001`-`RUF003`（ambiguous-unicode-character）は除外した。本プロジェクトの
  コメント・docstring は日本語で、全角括弧・読点は意図した表記であり誤検知しかしない。
- `restrict-template-expressions` は `allowNumber: true` にした。ID を URL に埋める
  用途で数値の文字列化は一意かつ安全で、このルールの主眼はオブジェクト・`null` の
  混入検出にある。
- 「関数長 30 行以下・引数 3 個以下・複雑度 10 以下・クラス 200 行以下」という
  定量基準は、Frontend は `sonarjs/cognitive-complexity` が見るが、Backend は
  現在の Ruff `select` に該当ルールが無く機械検証されていない。
  導入は `docs/Progress.md` の T1 として残す。
