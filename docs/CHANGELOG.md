# CHANGELOG — 完了した重要な変更の要約

新しいものを上に追記する。細かな進捗は書かない（Progress.md 完了時に要約を移す）。

## 2026-07 設計品質の定量基準を機械検証するようにした

CLAUDE.md が挙げていた定量基準（ネスト深度 3・関数長 30 行・引数 3 個・複雑度 10・
クラス長 200 行）はレビュー時の観点にとどまり、Backend では検証されていなかった。
まず既存コードの違反数を計測し（関数 407 個・クラス 128 個）、**基準どおりの閾値で
導入して既存の違反を直す**方針を採った（ADR-0012）。ほとんどの基準が違反 0 だったため。

- **Ruff**: `C901`(10) / `PLR0912`(8) / `PLR0913`(4) / `PLR0915`(30) を有効化。
- **AST テスト**（`tests/unit/test_design_metrics.py` 新規）: Ruff にルールが無い
  ネスト深度 3 とクラス長 200 行を検査する（依存方向テストと同じ方式）。
- 基準に対してずらしたのは 2 点だけ。**引数は 4 で検証**する（Ruff は `Depends()` や
  キーワード専用引数も数えるため）。**関数長は行数ではなく文の数**で見る（日本語の
  docstring や折り返した型注釈を数えると、説明を削る方向に働くため）。
- 基準に合わせて 3 か所を修正した。ログ一覧 API のクエリパラメータを
  `LogSearchRequest` へまとめ（OpenAPI 上のパラメータは不変）、
  **どこからも渡されていなかった `RestartRequestStore.save()` の `requested_at` 引数を削除**、
  依存方向テストの 5 段ネストを 2 段へ。
- `make check` と CI のコマンドは変わらない（`ruff check` と `pytest` に相乗り）。

## 2026-07 画面をスマートフォン対応にした

`index.css` にメディアクエリが 1 つも無く、390px 幅ではサイドバーが本文を圧迫し、
表がページ全体を横スクロールさせていた。ブレークポイント 1 つ（768px）を入れ、
狭い画面ではサイドバーを開閉式のドロワーにした（ADR-0011）。

- **ナビゲーション**: ヘッダーの ☰ で開閉。閉じるのは ✕ ・画面外タップ・Esc・
  項目の選択の 4 通り。開閉状態を持つのは新設の `components/AppLayout.tsx` で、
  **コンポーネントは画面幅を判定しない**（幅の解釈は CSS に閉じる）。
- **言語・テーマの選択**を `components/PreferenceControls.tsx` へ切り出し、狭い画面では
  ヘッダーではなくドロワーの下端に出す（ヘッダーが 3 段に折り返すのを避けるため）。
- **表**を `.table-scroll` で包み、表だけが横スクロールするようにした（6 画面）。
  ページ全体は横スクロールしない（390px で検証）。
- 入力欄・ボタンの最小高さを 2.75rem、文字を 16px にした（iOS Safari の自動拡大を防ぐ）。
  チェックボックスは枠ではなく目盛りを 1.5rem に拡大する。
- 横並びのフォーム（`.inline-form`）と設定行（`.config-row`）は縦に積む。
- **キーボード操作**: 開いたらドロワー内へフォーカスを移し、Tab をドロワー内で折り返し、
  閉じたらメニューボタンへ戻す（覆われて見えないヘッダーへ Tab で到達できてしまうため）。
  あわせて `visibility` の遷移時間を 0 にした。`visibility` は離散的に変わるため
  `transition: visibility 0.2s` と書くと切り替わりが遅れ、**開いた直後はまだ
  `hidden` = フォーカス不可**で `focus()` が黙って無視されていた（jsdom は CSS を
  適用しないためテストでは再現せず、実ブラウザでのみ起きる）。

## 2026-07 PWA アイコンを差し替えた（maskable を別画像に分けた）

アイコンを「白い F の文字」から稲妻マーク（対角グラデーションの角丸）に差し替えた。
あわせて**マニフェストの `maskable` が通常アイコンと同じ画像を指していた不具合を直した**。
Android はホーム画面のアイコンを円などに切り抜くため、セーフゾーンの無い画像では
ロゴの端が切れていた。`pwa-maskable-512x512.png`（全面塗り・図形を中央 42% に縮小）を
別に用意して割り当てた。iOS 用の `apple-touch-icon.png` は OS 側が角丸に切るため、
透明な角を持たない全面塗りにした。

配色と図形の正本は `scripts/generate_pwa_icons.py`（標準ライブラリだけで PNG を書き出す
生成スクリプト）で、`favicon.svg` を含む 5 ファイルすべてをそこから生成する。
手作業でアイコンを差し替えると SVG と PNG がずれるため、変更手順は `OPERATIONS.md` に置いた。

## 2026-07 DB のポートをホストへ公開しなくした

`db` は保守用に `127.0.0.1:3307:3306` をホストへ公開していたが、アプリは Docker
ネットワーク内部の `db:3306` へ接続するため、この公開は保守作業のためだけにあった。
`ports` を外して `expose: ["3306"]` だけにし、保守は `docker compose exec db mariadb ...`
とコンテナ内で完結させるようにした（ADR-0010）。ホストへ公開されるのは nginx の 1 ポートだけ。

- 設定キー `DB_BIND_ADDR` / `DB_HOST_PORT` を廃止した。`deploy.sh` が生成する `.env` にも
  `DB_HOST_PORT` を書かなくなった（stg / prod の分離はコンテナ名とネットワーク名で足りる）。
  **既存の `.env` に残っている行は compose が参照しないため無視される**（`deploy.sh` は
  既存の `.env` を書き換えないので、そのままデプロイできる）。次のデプロイでホスト側の
  3307 / 3308 が解放される。
- GUI クライアントから一時的につなぐ手順（socat のポートフォワード用コンテナ）を
  `OPERATIONS.md` に追加した。恒久的に開ける設定は持たない。
- **`docker compose exec` の資格情報は `sh -c '…'` でコンテナ内に展開させる。**
  `.env` は既定では資格情報の行がコメントアウトされており（値は compose の
  `${VAR:-default}` が供給する）、ホスト側のシェルに変数が無い。ダブルクォートで
  書くと空文字に展開されて接続に失敗する。既存の「管理者パスワード復旧」手順にも
  同じ誤りがあったので直した。

## 2026-07 CI の重複実行をなくした

`push`（全ブランチ）と `pull_request` の両方がトリガーだったため、**PR のあるブランチへ
push すると同じコミットが 2 回検証されていた**（Backend / Frontend × 2 イベント =
チェック 4 個）。内容は完全に同一で、CI 時間がそのまま二重になっていた。

`push` の対象を `main` だけに絞り、フィーチャーブランチは `pull_request` 側だけで
検証するようにした（ADR-0009）。あわせて `concurrency` を設定し、PR への連続 push では
古い実行をキャンセルする（`main` は「どのコミットが緑だったか」の記録を残すためキャンセルしない）。

**PR を作っていないブランチへの push では CI が走らなくなった。** PR を作れば全ゲートが走る。
効いていなかった `tags-ignore: ["v*"]` も削除した（`branches` を指定したワークフローは
タグ push に一致しないため元々無効。`v*` タグは `release.yml` の担当）。

## 2026-07 WEB 公開ポートの既定値を build-remote-container.env で指定できるようにした

デプロイ先の WEB 公開ポートは `deploy.sh` の環境別既定値（stg=8081 / prod=8080）か、初回
デプロイで生成された `.env` を手で直すしかなかった。8080 が空いていないホストでは
「一度失敗させてから `.env` を直して再実行」する手順になっていたため、
`build-remote-container.env` に `APP_WEB_HOST_PORT` を書けるようにした（ADR-0008）。

- `build-remote-container.sh` が `APP_WEB_HOST_PORT` を DEPLOY ステップへ引き継ぎ、
  `deploy.sh` が `.env` を新規生成するときの `WEB_HOST_PORT` に転記する。
  優先順位は `.env` ＞ `APP_WEB_HOST_PORT` ＞ 環境ディレクトリ名由来の既定値。
  既存の `.env` は従来どおり書き換えない。
- 値の検証（1〜65535 の整数）でデプロイを中断するのは、その値が実際に選ばれたときだけ。
  `.env` に `WEB_HOST_PORT` がある環境では使われないため、古い値・打ち間違いが残っていても
  デプロイは止めず警告で知らせる。先頭 0 付きの値は 8 進数と解釈される前に弾く。
- **`deploy.sh` が解決後の `WEB_HOST_PORT` を `export` するようにした（不具合修正）。**
  従来は compose へ渡っておらず、`.env` に `WEB_HOST_PORT` の行が無い環境では
  compose 側の既定値 8080 だけが効き、stg のヘルスチェック（8081）とずれていた。
  公開ポートとヘルスチェック URL が常に同じ値を見るようになった。

## 2026-07 画面仕様・ER 図の追加とドキュメント更新義務の明文化

「現在の仕様」を示すドキュメントが 2 種類欠けていたため追加し、更新義務を
CLAUDE.md に書いた（ADR-0007）。

- **`frontend/README.md`（新規）**: 画面遷移図（Mermaid）・画面一覧（ルートと必要
  scope）・画面ごとの仕様・利用者向けの操作マニュアル。これまでルートと画面の
  必要 scope は `App.tsx` と `Sidebar.tsx` を読まないと分からなかった。
- **`docs/ER.md`（新規）**: ER 図（Mermaid）・テーブル定義・モデリング規約。
  12 テーブルの関係、`log` が `users` へ FK を張らない理由（PII を持たない方針）、
  `account_security` の 3 テーブルが `ON DELETE CASCADE` である点を図に含めた。
- **CLAUDE.md**: 「変更したら必ず更新するドキュメント」の表を追加。画面を変えたら
  `frontend/README.md`、スキーマを変えたら `docs/ER.md` を**同じコミットで**更新する。
  あわせて `Progress.md` の運用（着手前に行を追加し、完了時に削除。「✅完了」は作らない）
  と ADR の基準（対象・採番規則・承認済みは書き換えず置き換える）を明文化した。

**初期管理者のパスワードを `admin` から `admin@example.com` に変更した。**
平文は `master_data.DEFAULT_ADMIN_PASSWORD` に定数として持たせ、事前計算ハッシュ
（`DEFAULT_ADMIN_PASSWORD_HASH`）との対応を `tests/unit/test_master_data.py` が検証する。
Domain 層は werkzeug を import できないため、ハッシュ生成をここに置けないため。
テストからパスワード文字列の直書きも無くした。

## 2026-07 品質ゲートの必須化（整形・静的解析・型・テスト）

CI を「Lint → Type Check → Test」の必須ゲートにした（ADR-0006）。
Backend 4 種・Frontend 4 種の計 8 ゲートで、落ちたらマージできない。
経緯は `history/2026-07-quality-gates.md`。

導入したツールと、それによって見つかった実際の不具合:

- **Ruff Format**（新規）。162 ファイル中 100 ファイルが未整形だった。一括整形した。
  `line-length` を 100 → 120 に上げ、`E501` の一律除外をやめた。
- **Ruff Check の拡張**。`select` に `C4` / `ARG` / `N` / `RET` / `PTH` / `RUF` を追加。
  `DomainException` → `DomainError`（N818）、`int(round(...))` の二重変換（RUF046）、
  未使用引数、`__all__` の未ソート、効かない `# noqa` 14 件を整理した。
- **MyPy strict**（新規）。本番コードとテストの両方を対象にし、114 件を修正。
  - `RestartWatcher` が具象 `RestartRequestStore` に依存していた **DIP 違反**を検出。
    `RestartRequestReader` Protocol を切り出し、watcher はそれだけに依存するようにした。
    テストダブルを渡すのに具象クラスの継承が要らなくなった。
  - `sessionmaker` / `dict` / `Callable` の型引数漏れ、`Result` に無い `rowcount` への
    アクセス、`FromClause.insert()`（`sa.insert(Log)` へ修正）を検出。
  - `require_permission()` が戻り値の型を持っていなかった（依存関数ファクトリ）。
- **TypeScript の追加フラグ**。`noUncheckedIndexedAccess` /
  `exactOptionalPropertyTypes` / `noImplicitOverride` /
  `noFallthroughCasesInSwitch` を有効化。空配列を前提にした `locales[0]`、
  `choices` を `string[][]` と緩く持っていた箇所（`[value, label]` のタプルへ）、
  `fetch` に `body: undefined` を渡していた箇所を直した。
- **ESLint**（新規）。`strictTypeChecked` + `react-hooks` + `sonarjs` で 74 件。
  最多は **`no-misused-promises` 19 件**で、`onSubmit={submit}` のように async 関数を
  そのままハンドラへ渡し、Promise を投げ捨てていた箇所。内部で `catch` 済みなので
  `void` で明示に変えた。`main.tsx` の非 null 断言、`response.json()` の `any`、
  `String(unknown)` による `[object Object]` の混入も直した。
- **Vitest**（新規）。Frontend にテストが 1 本も無かったため 27 件を追加
  （i18n の言語選択・プレースホルダ、テーマの OS 追従と購読解除、API クライアントの
  トークン保持とエラーコード変換、UI 設定取得のフォールバック）。
- **DDD 依存方向の検証**（新規）。`tests/unit/test_layer_dependencies.py` が AST で
  「Domain は Application / Infrastructure / Presentation を import しない」
  「Application は Infrastructure / Presentation へ依存しない」
  「Domain は FastAPI / SQLAlchemy 等に依存しない」を検証する（93 ケース）。

`make check` で CI と同じものを手元で流せる（`make format` で自動整形）。

## 2026-07 二要素認証・パスキー・テーマ切り替え・自己再起動

photonest を参考に 5 つの機能を追加し、重複していた処理を整理した。

- **二要素認証（TOTP）とパスキー（WebAuthn）** を
  `bounded_contexts/account_security/` として追加（ADR-0003）。
  移植元にあった 2 つの問題を設計で直した。
  - 共有鍵を `users` の列ではなく `totp_secrets` テーブルに置き、確認できるまで
    有効にしない 2 段階登録にした（QR の読み取り失敗で締め出されないように）。
  - WebAuthn チャレンジをプロセス内 `dict` ではなく `webauthn_challenges` テーブルに
    置いた。移植元の実装は単一プロセス専用で、既定の Gunicorn `--workers=2` では
    発行と検証が別ワーカーに当たった瞬間に必ず失敗する状態だった。
  - `pyotp` / `webauthn` は Infrastructure に閉じ込め、Domain には Protocol だけを置いた。
- **設定変更による自己再起動** を `shared/kernel/restart/` として追加（ADR-0004）。
  起動時にしか読まれない設定（`LOG_LEVEL` / `LOG_TO_DATABASE` /
  `CORS_ALLOWED_ORIGINS`）は保存しても反映されず、画面上は成功と出ていた。
  保存 API が `restart_required` を返し、`POST /api/admin/system/restart` で
  再起動を要求できるようにした。
- **テーマ切り替え**（light / dark / OS 追従）を追加。配色を CSS 変数へ移し、
  `<html data-theme>` で切り替える。以前はブラウザ任せの `Canvas` /
  `CanvasText` を使っており、アプリ側から配色を選べなかった。
- **日英切り替えの仕上げ**。`LANGUAGES` / `DEFAULT_LOCALE` は定義済みだったが
  参照するコードが無く、管理画面に並ぶだけで何も動かしていなかった。
  公開エンドポイント `GET /api/ui/settings` で配り、実際に効くようにした
  （ADR-0005）。管理画面の設定ラベル・選択肢も辞書で訳せるようにし、
  訳の抜けを `tests/unit/test_i18n_dictionaries.py` が検出する。

重複処理の整理:

- `POST /api/admin/maintenance/shutdown` を削除。自プロセスへ SIGTERM を送るだけで、
  Gunicorn 配下ではワーカーが 1 つ落ちてアービターが同じ環境で作り直すため、設定は
  反映されなかった。終了方法の判断を `build_process_terminator()` に集約し、
  `POST /api/admin/system/restart` へ一本化した。
- `system_settings` テーブルを短命コネクションで読む生 SQL が設定解決と再起動要求で
  重複していたため、`SystemSettingRecordReader` に集約した。
- アクセストークン Cookie の付与を `set_access_token_cookie()` に集約
  （パスワード・リフレッシュ・パスキーの 3 経路が同じ属性を使う）。
- `utcnow()` を `shared/kernel/timestamps.py` へ移動（Application 層からも使うため）。
- フロントエンドの 7 か所に散っていた「例外 → `error.<code>` 翻訳キー」変換を
  `errorMessageKey()` に集約した。

## 2026-07 ビルド／デプロイ最新化・PWA 対応

- ビルドを `scripts/build.sh` に集約（idp と同方式）。`dist/` に image tar・`deploy.sh`・
  `manifest.env`／`manifest.sha256`（checksum・イメージ ID 照合）を出力する。
- git 非搭載のデプロイ先向けに `scripts/build-remote-container.sh` を導入
  （dev コンテナ内で SYNC → BUILD → PICK → DEPLOY を一括実行。self-update 対応）。
- `deploy.sh` の配置を dist 直下（`<env>/deploy.sh`）に統一（旧 `<env>/scripts/deploy.sh`
  配置は廃止）。manifest による tar 検証とロード済みイメージの再利用を追加。
- DB のホスト公開ポートを既定でループバック（127.0.0.1）に限定（`DB_BIND_ADDR`）。
  公開ポートは nginx のみ。
- フロントエンドを PWA 化（vite-plugin-pwa: Web App Manifest・Service Worker 自動更新・
  アイコン一式。`/api` 等はナビゲーションフォールバック対象外）。

## 2026-07 テンプレート刷新（photonest 準拠）

- photonest の構成・設計思想をベースに全面刷新。
  DDD 4層 + bounded_contexts 構成、scope ベース認可（JWT）、
  システム設定管理（環境変数 > DB > デフォルト）、構造化ログ（JSON + DB）、
  React SPA スケルトン、Docker（db / web / nginx）、デプロイスクリプトを導入。
- アルバム・メディア・バッチ（Celery / Redis）・wiki・Google 連携は持ち込まない。
- 設計判断は ADR-0001（DB エンジン）・ADR-0002（認証スコープ）を参照。
