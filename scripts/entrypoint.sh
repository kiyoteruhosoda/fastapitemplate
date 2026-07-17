#!/bin/sh
set -eu

# ===== Colored echo =====
log()  { printf "\033[32m[entrypoint]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[entrypoint][warn]\033[0m %s\n" "$*"; }

# ===== Startup diagnostics =====
log "========== DIAGNOSTICS =========="

if [ -f /app/shared/kernel/version.json ]; then
  python -c "
import json
try:
    d = json.load(open('/app/shared/kernel/version.json'))
    print('[entrypoint] image : version={} branch={} commit={} build={}'.format(
        d.get('version','?'), d.get('branch','?'),
        d.get('commit_hash','?'), d.get('build_date','?')))
except Exception as e:
    print('[entrypoint] image : version.json parse error -', e)
" 2>&1
else
  warn "image : version.json not found (local build?)"
fi

log "python : $(python --version 2>&1)"
log "mode   : ${1:-web}"
log "================================="

# ===== DB wait（MariaDB 使用時のみ） =====
if echo "${DATABASE_URI:-}" | grep -q "mysql"; then
  export _DB_URI="$DATABASE_URI"
  log "Waiting for DB ..."
  until python -c "
import os, sys
from urllib.parse import urlparse
import pymysql
u = urlparse(os.environ['_DB_URI'].replace('mysql+pymysql', 'mysql'))
try:
    pymysql.connect(host=u.hostname, port=u.port or 3306,
                    user=u.username, password=u.password or '',
                    connect_timeout=3).close()
except Exception:
    sys.exit(1)
" >/dev/null 2>&1; do
    printf "."
    sleep 2
  done
  unset _DB_URI
  printf "\n"
  log "DB is ready"
fi

# ===== Trap =====
term_handler() {
  warn "Signal received, stopping..."
  kill -TERM "$child" 2>/dev/null || true
  wait "$child" 2>/dev/null || true
  log "Shutdown complete"
  exit 0
}
trap term_handler TERM INT

# ===== Mode selection =====
MODE="${1:-web}"
shift || true

case "$MODE" in
  web)
    log "Running DB migrations"
    python scripts/run_db_migrations.py
    log "Starting Gunicorn + UvicornWorker (ASGI web mode)"
    exec gunicorn asgi:app \
      --worker-class uvicorn.workers.UvicornWorker \
      --workers "${GUNICORN_WORKERS:-2}" \
      --bind 0.0.0.0:8000 \
      --timeout 120 \
      --graceful-timeout 30 \
      --access-logfile - \
      --error-logfile -
    ;;
  migrate)
    log "Running DB migrations only"
    exec python scripts/run_db_migrations.py
    ;;
  *)
    exec "$MODE" "$@"
    ;;
esac
