#!/bin/sh
set -eu

log() { printf '%s %s\n' "[product-bootstrap]" "$*"; }

CONFIG_DIR="${PRODUCT_CONFIG_DIR:-/data/config}"
REPORTS_DIR="${REPORTS_DIR:-/data/reports}"
DATA_DIR="${DATA_DIR:-/data}"
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"

log "Preparing persistent directories"
mkdir -p "$CONFIG_DIR" "$REPORTS_DIR" "$DATA_DIR/runtime"
chmod 700 "$CONFIG_DIR" || true
chmod 755 "$REPORTS_DIR" "$DATA_DIR/runtime" || true

log "Checking writable storage"
for dir in "$CONFIG_DIR" "$REPORTS_DIR" "$DATA_DIR/runtime"; do
  probe="$dir/.write-test"
  : > "$probe"
  rm -f "$probe"
done

log "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}"
python - <<'PY'
import os, socket, sys, time
host=os.getenv('POSTGRES_HOST','db')
port=int(os.getenv('POSTGRES_PORT','5432'))
deadline=time.time()+90
last=None
while time.time()<deadline:
    try:
        with socket.create_connection((host,port),timeout=3):
            print('[product-bootstrap] PostgreSQL socket is ready', flush=True)
            sys.exit(0)
    except OSError as exc:
        last=exc
        time.sleep(2)
print(f'[product-bootstrap] PostgreSQL is unavailable: {last}', file=sys.stderr)
sys.exit(1)
PY

if [ -z "${DATABASE_URL:-}" ]; then
  log "DATABASE_URL is missing; refusing unsafe startup"
  exit 1
fi

log "Starting Channel Analyzer Bot"
exec python -m app.entrypoint
