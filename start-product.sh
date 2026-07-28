#!/bin/sh
set -eu

PRODUCT_URL="http://localhost:${CONTROL_CENTER_PORT:-8080}"

say() { printf '%s\n' "$*"; }
fail() { say "ERROR: $*"; exit 1; }

command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Install Docker Desktop and run this file again."
docker compose version >/dev/null 2>&1 || fail "Docker Compose is unavailable. Update Docker Desktop."

say "Starting Channel Analyzer Bot..."
docker compose up -d --build

say "Waiting for Control Center..."
i=0
while [ "$i" -lt 60 ]; do
  if python3 - "$PRODUCT_URL/health" <<'PY' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=2).read()
PY
  then
    say "Channel Analyzer Bot is ready: $PRODUCT_URL"
    case "$(uname -s 2>/dev/null || true)" in
      Darwin*) open "$PRODUCT_URL" >/dev/null 2>&1 || true ;;
      Linux*)  xdg-open "$PRODUCT_URL" >/dev/null 2>&1 || true ;;
    esac
    exit 0
  fi
  i=$((i+1))
  sleep 2
done

docker compose ps
fail "The product did not become ready in time. Run: docker compose logs app"
