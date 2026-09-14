#!/usr/bin/env bash
# Served-instance load smoke: start a real uvicorn process, wait for liveness,
# then drive the same smoke workload over HTTP.
#
# This complements the in-process smoke. The ASGI transport never opens a
# socket, so server startup, real HTTP handling, and middleware order stay
# unverified without it. No database is required; set
# RUNTIME_STORE_DATABASE_URL to smoke a PostgreSQL-backed instance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PORT="${SERVED_LOAD_SMOKE_PORT:-8765}"
BASE_URL="http://127.0.0.1:${PORT}"
LOG_FILE="$(mktemp -t served-load-smoke-XXXXXX)"

python -m uvicorn apps.api.main:app \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --log-level warning >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "${SERVER_PID}" 2>/dev/null || true
  wait "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup EXIT

if ! python - "${BASE_URL}" <<'PY'
import sys
import time
import urllib.error
import urllib.request

base_url = sys.argv[1]
for _ in range(60):
    try:
        with urllib.request.urlopen(f"{base_url}/api/health/live", timeout=1) as response:
            if response.status == 200:
                raise SystemExit(0)
    except (OSError, urllib.error.URLError):
        time.sleep(0.5)
raise SystemExit(f"served API did not become live on {base_url}")
PY
then
  echo "--- uvicorn log ---"
  tail -n 40 "${LOG_FILE}" || true
  exit 1
fi

python scripts/ops/load_smoke.py \
  --base-url "${BASE_URL}" \
  --requests 120 \
  --concurrency 8 \
  --p95-threshold-ms 2000 \
  --error-rate-threshold 0.05
