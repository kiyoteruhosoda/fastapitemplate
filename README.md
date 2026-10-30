# fastapitemplate

FastAPI（DDD の 4 層）＋ React の Web アプリを始めるための**テンプレート**です。
認証・SSO・認可（ロールと scope）・テナント・設定・ログと監査・通知・管理画面・k3s への配布までが
入った状態から、自分の機能だけを書き足して使います。

**使い方は [docs/TEMPLATE.md](docs/TEMPLATE.md) にまとめてあります**
（新しいアプリの作り方・名前の付け替え・見本の消し方・機能の足し方・雛形の更新の取り込み方）。

⚠ **このテンプレートから作ったアプリは、名前を必ず変えてください。** `fastapitemplate` のまま配ると、
雛形由来のほかのアプリとイメージや置き場を取り合います（[ADR-0073 §1](docs/decisions/ADR-0073-build-and-deploy.md)）。

## 技術スタック

- Python 3.15 / uv / FastAPI + Pydantic（API の仕様は `/docs`・`/openapi.json`）
- SQLAlchemy 2.x + Alembic（本番 MariaDB 10.11 / 開発・テスト SQLite）
- React + TypeScript + Vite（`frontend/`。日英・テーマ・PWA）
- コンテナイメージ 1 つを k3s へ（Gunicorn + UvicornWorker と nginx）
- 品質ゲート: Ruff / MyPy（strict）/ PyTest ・ Prettier / ESLint / TypeScript / Vitest ・ Playwright（煙試験）

## 入っている機能

| 区分 | 中身 |
|---|---|
| 認証 | パスワード・二要素認証（TOTP）・パスキー・パスワードリセット・ログイン試行の制限 |
| SSO | 外部 IdP（OIDC）でのサインイン・IdP での停止の反映 |
| 認可 | scope（権限コード）とロール。ロールは使う人（アクター）から導く（[ADR-0084](docs/decisions/ADR-0084-actors-and-roles.md)） |
| テナント | 組織ごとの区切り。テナントの外に運用者とサポート担当 |
| 設定 | システム設定（全体）とコンテンツ設定（テナントごと）を画面から変える |
| 記録 | アプリログと監査ログ（画面で検索）・保持期間の掃除 |
| 通知 | お知らせ（ベル・Web Push・FCM）とメール |
| 運用 | `/healthz`・`/readyz`・`/info`・`/metrics`・画面からの再起動・メンテナンス画面 |

見本として、アイテム（いちばん小さな機能）と共有メモ（1 件ずつ可否が変わる機能）が入っています。
自分の機能ができたら消します（[docs/TEMPLATE.md](docs/TEMPLATE.md) 2.5）。

## クイックスタート（手元）

```bash
uv sync
uv run alembic upgrade head          # スキーマとマスタデータ（SQLite: app.db）
uv run python main.py                # http://127.0.0.1:8000（Swagger は /docs）
```

```bash
cd frontend && npm install && npm run dev    # http://localhost:5173（/api はプロキシ）
```

初期管理者は `admin@example.com` / `admin@example.com` です（本番ではこのパスワードでは入れません）。
パスキーを試すときは `127.0.0.1` ではなく `localhost` で開きます。

品質ゲートは CI が PR ごとに流します。手元で流すときは `make check`（自動整形は `make format`）。

## 配布

main へマージすると、deck（https://deck.nolumia.com）がイメージのビルド → digest の固定 → k3s への反映を
自動で行います。宣言の雛形と手順は [deploy/k8s/README.md](deploy/k8s/README.md) です。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/TEMPLATE.md](docs/TEMPLATE.md) | **テンプレートの使い方**（ここから読む） |
| [CLAUDE.md](CLAUDE.md) | 守るべき設計規則・文書の運用 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | レイヤー構成・設計の解説 |
| [docs/ER.md](docs/ER.md) | ER 図・テーブル定義 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 操作の手順書（「〇〇したいとき」） |
| [docs/decisions/](docs/decisions/README.md) | 設計判断（ADR） |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 変更履歴（雛形の更新を取り込むときに読む） |
| [frontend/README.md](frontend/README.md) | 画面遷移図・画面仕様・操作マニュアル |
| [deploy/k8s/README.md](deploy/k8s/README.md) | k3s への配布（宣言の雛形つき） |
| [scripts/README.md](scripts/README.md) | 同梱のスクリプト |
| `bounded_contexts/*/README.md` | 各コンテキストの仕様（audit・account_security・identity_federation） |

## ライセンス

[LICENSE](LICENSE) を参照。
