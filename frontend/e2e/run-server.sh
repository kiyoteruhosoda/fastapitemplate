#!/usr/bin/env bash
# E2E 用に本物のサーバーを 1 つ立てる（ADR-0072 §6）。playwright.config.ts の webServer から呼ばれ、
# 画面のビルド（frontend/dist）はその前に済んでいる。FastAPI が dist をそのまま配る。
#
# DB は毎回まっさらな SQLite を作り、マイグレーションで初期管理者まで入れる
# （パスワードは webServer が渡す ADMIN_INITIAL_PASSWORD）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

DB_DIR="$(mktemp -d)"

export TESTING="true"
export DATABASE_URI="sqlite:///${DB_DIR}/e2e.db"
# 手元の .env に本番寄りの値があっても、ここで決めた値が勝つ（load_dotenv は上書きしない）。
# http で試すので Secure の Cookie は使えない。入り口はパスワードのログインだけにする。
export SESSION_COOKIE_SECURE="false"
export LOCAL_LOGIN_ENABLED="true"
export OIDC_ENABLED="false"

echo "[e2e] applying migrations to ${DATABASE_URI}"
uv run python scripts/run_db_migrations.py

echo "[e2e] starting uvicorn on 127.0.0.1:${E2E_PORT:-8100}"
exec uv run uvicorn asgi:app --host 127.0.0.1 --port "${E2E_PORT:-8100}"
