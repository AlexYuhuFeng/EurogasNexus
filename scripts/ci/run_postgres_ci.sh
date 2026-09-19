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

# Owner decision D1: every profile identifies its callers, so this smoke presents the deployment
# token - the documented SDK/CLI caller - exactly as the SDK and the CLI do. Without one it would
# measure a fail-closed 503 instead of the read it exists to check.
token = os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "").strip()
if not token:
    raise SystemExit(
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN must be configured: the API identifies its callers in "
        "every profile now, so an uncredentialed smoke asserts nothing about the database."
    )

client = TestClient(app, headers={"X-Eurogas-Api-Key": token})
response = client.get("/api/route-cost/tso-tariffs")
assert response.status_code == 200, response.text
meta = response.json()["meta"]
assert meta["source_references"] == ["runtime-postgresql"], meta
print("db-backed api smoke ok: tso-tariffs served from runtime-postgresql")

# The refusal the posture guarantees, asserted where a real deployment would see it: no credential,
# no read.
anonymous = TestClient(app)
refused = anonymous.get("/api/route-cost/tso-tariffs")
assert refused.status_code in {401, 403, 503}, refused.status_code
print("db-backed api smoke ok: an uncredentialed caller is refused")
PY

python -m pytest -q \
  tests/integration/test_postgres_backed_smoke.py \
  tests/integration/test_research_entitlement_postgres.py
