#!/usr/bin/env bash
# Start one real server for E2E (ADR-0072 §6). Called from webServer in playwright.config.ts;
# the frontend build (frontend/dist) is already done by then. FastAPI serves dist as is.
#
# Each run creates a fresh SQLite DB; migrations insert everything up to the initial admin
# (password is ADMIN_INITIAL_PASSWORD passed by webServer).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

DB_DIR="$(mktemp -d)"

export TESTING="true"
export DATABASE_URI="sqlite:///${DB_DIR}/e2e.db"
# Values set here win even if the local .env has production-like values (load_dotenv does not
# override). Testing over http, so Secure cookies can't be used. Only password sign-in is enabled.
export SESSION_COOKIE_SECURE="false"
export LOCAL_LOGIN_ENABLED="true"
export OIDC_ENABLED="false"

echo "[e2e] applying migrations to ${DATABASE_URI}"
uv run python scripts/run_db_migrations.py

echo "[e2e] starting uvicorn on 127.0.0.1:${E2E_PORT:-8100}"
exec uv run uvicorn asgi:app --host 127.0.0.1 --port "${E2E_PORT:-8100}"
