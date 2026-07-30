# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

- 状態: ⬜未着手 / 🚧進行中 / 🟡要判断
- 影響度・工数: 大 / 中 / 小

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T4 | 画面をスマホ対応にする（レスポンシブ・ナビゲーション） | 🚧進行中 | 中 | 中 |
| 2 | T1 | Backend の定量的な設計品質基準（関数長・引数数・複雑度）を機械検証する | 🚧進行中 | 中 | 中 |

## 詳細

### T4 画面をスマホ対応にする

`frontend/src/index.css` にメディアクエリが 1 つも無く、幅の狭い端末では
サイドバー（`min-width: 12rem`）が本文を圧迫し、表（`table`）が画面外へはみ出す。
ブレークポイントを 1 つ入れ、サイドバーを開閉式のドロワーにする。
画面の操作手順が変わるため `frontend/README.md` も更新する。

### T1 Backend の定量的な設計品質基準を機械検証する

開発標準は「関数長 30 行以下・引数 3 個以下・ネスト 3 段以下・複雑度 10 以下
（推奨 5 以下）・クラス 200 行以下」を基準として挙げているが、Backend では
機械検証されていない。ADR-0006 で採用した Ruff の `select`
（`E, F, I, B, UP, SIM, C4, ARG, N, RET, PTH, RUF`）に該当ルールが含まれないため。

Frontend は `sonarjs/cognitive-complexity`（15）が複雑度のみ見ている。

候補となる Ruff ルール:

| ルール | 基準 | 設定キー |
|---|---|---|
| `C901` | 循環複雑度 | `[tool.ruff.lint.mccabe] max-complexity` |
| `PLR0913` | 引数の数 | `[tool.ruff.lint.pylint] max-args` |
| `PLR0912` | 分岐の数 | `[tool.ruff.lint.pylint] max-branches` |
| `PLR0915` | 文の数（関数長の代替） | `[tool.ruff.lint.pylint] max-statements` |

要判断としていた理由（既存の違反数が分からないと閾値を決められない）は計測で解消した。
計測結果と採用する閾値は ADR に残す。関数長そのもの（30 行）とクラス長（200 行）、
ネスト深度（3 段）に対応する Ruff ルールは無いため、`tests/unit/` の AST テストで見る
（`test_layer_dependencies.py` と同じ方式）。

（テンプレート刷新の経緯は `history/2026-07-template-refresh.md`、
品質ゲート導入の経緯は `history/2026-07-quality-gates.md`、
要約は `CHANGELOG.md` を参照）
