#!/usr/bin/env bash
# PostgreSQL CI: apply migrations, verify the required-table contract, and
# smoke-test DB-backed API reads against a real PostgreSQL instance.
# Requires RUNTIME_STORE_DATABASE_URL pointing at a reachable PostgreSQL.
set -euo pipefail

alembic upgrade head

python - <<'PY'
import os

from sqlalchemy import create_engine

from eurogas_nexus.db.registry import list_missing_required_tables

url = os.environ["RUNTIME_STORE_DATABASE_URL"]
engine = create_engine(url)

missing = list_missing_required_tables(engine)
if missing:
    raise SystemExit(f"missing required tables after upgrade: {sorted(missing)}")
print("postgres schema ok: all required tables present")

from fastapi.testclient import TestClient  # noqa: E402

from apps.api.main import app  # noqa: E402

client = TestClient(app)
response = client.get("/api/route-cost/tso-tariffs")
assert response.status_code == 200, response.text
meta = response.json()["meta"]
assert meta["source_references"] == ["runtime-postgresql"], meta
print("db-backed api smoke ok: tso-tariffs served from runtime-postgresql")
PY

python -m pytest -q tests/integration/test_postgres_backed_smoke.py
