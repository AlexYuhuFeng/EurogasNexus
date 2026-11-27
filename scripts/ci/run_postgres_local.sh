#!/usr/bin/env bash
# Run the hosted "PostgreSQL integration" job on this machine, against a throwaway PostgreSQL 16
# container, with the same environment `.github/workflows/ci.yml` gives it.
#
# The pre-push gate has no database, so a change that adds a migration can pass it and still
# fail hosted CI (it did on 2026-11-27: a test pinned to the previous schema head). Run this
# before pushing any change that touches `alembic/`, `src/eurogas_nexus/db/` or
# `tests/integration/`. Needs Docker.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
name="eurogas-nexus-pgci-$$"
port="${EUROGAS_NEXUS_LOCAL_PG_PORT:-55433}"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name "$name" -e POSTGRES_USER=nexus -e POSTGRES_PASSWORD=nexus \
  -e POSTGRES_DB=nexus_test -p "127.0.0.1:${port}:5432" postgres:16 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$name" pg_isready -U nexus -d nexus_test >/dev/null 2>&1 && break
  sleep 1
done
export RUNTIME_STORE_DATABASE_URL="postgresql+pg8000://nexus:nexus@127.0.0.1:${port}/nexus_test"
export EUROGAS_NEXUS_PUBLIC_API_TOKEN="ci-integration-public-api-token"
bash scripts/ci/run_postgres_ci.sh
