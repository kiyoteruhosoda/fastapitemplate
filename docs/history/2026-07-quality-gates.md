# 2026-07 品質ゲート導入の経緯

React + FastAPI（DDD / OOP / SOLID）の開発標準として、CI に整形・静的解析・型・
テストの品質ゲートを入れた作業の記録。判断は ADR-0006、要約は CHANGELOG を参照。

## 着手前の状態

CI は 2 ジョブだけだった。

- Backend: `uv run ruff check .`（`select = [E, F, I, UP, B, SIM]`、`E501` 除外）と `uv run pytest`
- Frontend: `npm run build`（= `tsc && vite build`）

つまり **Backend に型チェックが無く、Frontend にテストが無く、両方に整形の強制が
無かった**。`ruff format` は設定すらされておらず、Prettier も入っていなかった。

## 直した内容と、実際に出てきた件数

導入は「設定を入れる → 出た指摘を潰す」の順で進めた。指摘の総数は次のとおり。

| ツール | 初回検出 | 内訳の概要 |
|---|---|---|
| Ruff Format | 100 ファイル | 未整形（162 ファイル中） |
| Ruff Check | 468 → 31 件 | 437 件は日本語コメントの RUF002/003 誤検知（除外設定で解消） |
| MyPy strict | 114 件 | 本番 14 件 / テスト 100 件 |
| TypeScript | 4 件 | 追加フラグ 4 種による |
| ESLint | 70 件 | 自動修正 33 件を含む |

### Ruff の RUF002/RUF003 は誤検知だった

`select` に `RUF` を足した直後、468 件のうち 437 件が
`ambiguous-unicode-character-docstring` / `-comment` だった。本プロジェクトの
コメント・docstring は日本語で、`（` `）` `、` は意図した表記である。
`RUF001`-`RUF003` を `ignore` に入れて解消した。残り 31 件が本物で、22 件は
`--fix` で、9 件を手で直した。

`line-length` を 100 → 120 に上げた結果、`E501` の一律除外が不要になった
（120 超の行は 1 本も無かった）。

### MyPy がテストに掛かることで DIP 違反が出た

テストを型付けの対象外にする選択も取れたが、テストを含めた。その結果、
`tests/unit/test_restart_watcher.py` の `_StubStore` を
`RestartWatcher(store=...)` に渡している箇所が型エラーになった。

```
Argument "store" to "RestartWatcher" has incompatible type "_StubStore";
expected "RestartRequestStore | None"
```

`RestartWatcher.__init__` が具象クラス `RestartRequestStore` を型として要求していた。
同居する `terminator` は `ProcessTerminator` Protocol なのに、`store` だけが具象に
依存していた。CLAUDE.md「設計方針」の DIP に反する。

`shared/kernel/restart/request.py` に `RestartRequestReader` Protocol
（`load(scope) -> RestartRequest | None` のみ）を切り出し、watcher はそれだけに依存する
ようにした。テストを型付けしなければ気付かなかった。

本番コードの残り 13 件は型引数漏れ（`sessionmaker`・`dict`・`Callable`）と、
SQLAlchemy のスタブ上に存在しないメンバーへのアクセス
（`Result.rowcount` → `CursorResult` へ cast、`Log.__table__.insert()` → `sa.insert(Log)`）
が中心だった。テスト側 100 件はほぼ「フィクスチャ引数の注釈漏れ」で、
`client: TestClient` / `admin_headers: dict[str, str]` 等を機械的に付けた。

### ESLint の最多は Promise の投げ捨てだった

74 件のうち 19 件が `@typescript-eslint/no-misused-promises` で、すべて
`onSubmit={submit}` / `onClick={() => remove(user)}` のように async 関数を
そのままハンドラへ渡している箇所だった。いずれも関数内部で `try/catch` して
`notify('error', ...)` しているため実害は出ていなかったが、返る Promise は
誰も見ていない状態だった。`void submit(e)` のように**捨てていることを明示**する形へ変えた。

他に、`main.tsx` の `document.getElementById('root')!`（非 null 断言 →
明示的な throw）、`tryRefresh()` の `await response.json()` が `any` のまま
`setTokens()` に渡っていた箇所（`TokenPair` 型を定義）、設定値の表示で
`String(unknown)` により `[object Object]` が出得た箇所を直した。

`restrict-template-expressions` の 5 件は `` `/api/admin/roles/${role.id}` `` のような
数値の埋め込みで、`allowNumber: true` を設定して許可した。

### TypeScript の追加フラグ

`noUncheckedIndexedAccess` で `initialLocale()` の `return locales[0]` が
`Locale | undefined` になった。`availableLocales()` は必ず 1 件以上返すが型では
表せないため、`FALLBACK_LOCALE` 定数を置いて `locales[0] ?? FALLBACK_LOCALE` にした。

`exactOptionalPropertyTypes` で `fetch(path, { body: undefined })` が弾かれた。
`RequestInit` を組み立てて `body` があるときだけ差し込む形にした。

`ConfigPage` の `choices?: string[][]` は `[value, label]` に分解して使っており、
添字アクセスが `string | undefined` になった。API の契約どおり
`[value: string, label: string][]` のタプルに直した（型が実態に合っていなかった）。

`theme/index.tsx` の `window.matchMedia?.(...)` は、`lib.dom` の型上 `matchMedia` が
必須なため `no-unnecessary-condition` で落ちた。オプショナルチェーンを外した。
jsdom は `matchMedia` を実装しているが `change` を通知しないため、テストでは
`vi.stubGlobal` で差し替えている。

### Frontend のテストは新規に 27 件書いた

テストが 1 本も無かったため、`vitest run` を意味のあるゲートにするところから始めた。
対象は振る舞いが分岐する部分を選んだ。

- i18n: 「利用者の選択 > ブラウザ > サーバー既定値」の優先順位、選べない言語が
  保存されていた場合、未知の言語しか無い場合、`<html lang>` の追従、
  プレースホルダの差し込みと未指定時の据え置き
- theme: 同じ優先順位、`system` での OS 追従、明示選択時に OS 変化を無視すること、
  `<html data-theme>` と `colorScheme` への反映、アンマウント時の購読解除
- API クライアント: `ApiError` → `error.<code>` 変換、非 `ApiError` の丸め、トークン保持
- UI 設定: サーバー応答／エラー応答／通信失敗それぞれのフォールバック

「Provider の外でフックを使うと投げる」テストは、React が例外を `console.error` と
window の `error` イベントにも流し、jsdom がそれを標準エラーへ出す。通ったテストが
失敗のように見えるため、`src/test-support/renderErrors.ts` の
`withSuppressedRenderErrors()` で想定内の例外だけ黙らせている。

### 依存方向の検証で分かったこと

`tests/unit/test_layer_dependencies.py` を書く際、最初は
「Presentation が import してよいのは Application / Domain / Presentation だけ」
という表で組んだところ 11 件落ちた。すべて `presentation → shared.infrastructure.models`
（SQLAlchemy モデル）で、実際には 17 か所ある。

これは開発標準が明示的に禁止している向き（`Domain → Infrastructure`、
`Domain → Presentation`、`Application → Presentation`）には含まれない。最も外側の層が
具体実装を組み立てて `Depends()` に渡すのは Clean Architecture でも正しい向きで、
DI の配線はどこかで行う必要がある。禁止するなら組み立て責務を Application へ移す
別の設計判断が必要になるため、ルールを「逆流の禁止」に絞り直した。

現状のレイヤー間の実際の辺は次の 5 本で、禁止対象の辺は 1 本も無い。

```
application    → domain          23
infrastructure → domain          15
presentation   → application     19
presentation   → domain           6
presentation   → infrastructure  17   ← 禁止しない（DI の配線）
```

検証が実際に効くことは、`bounded_contexts/example/domain/entities/item.py` に
Infrastructure の import を一時的に足して落ちることを確認した。

## 残したもの

「関数長 30 行以下・引数 3 個以下・ネスト 3 段以下・複雑度 10 以下・クラス 200 行以下」
という定量基準は、Frontend は `sonarjs/cognitive-complexity`（15）が部分的に見るが、
Backend は開発標準が指定した Ruff の `select` に該当ルールが無く、機械検証されていない。
`C901` / `PLR0912` / `PLR0913` / `PLR0915` の追加が候補で、既存コードの違反数を
数えてから閾値を決める必要がある。`docs/Progress.md` の T1 として残した。
