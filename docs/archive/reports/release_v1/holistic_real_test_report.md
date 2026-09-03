# Holistic Real Runtime Test Report

Date: 2026-06-27

## Scope Tested

This validation ran the current Eurogas Nexus repository against the local
PostgreSQL runtime server provided by the operator.

Validated surfaces:

- Alembic migration to repository head.
- PostgreSQL runtime validator.
- Official/public or operator-keyed ingestion into PostgreSQL.
- FastAPI app import and DB-backed `/api` routes.
- European explicit-leg route-cost tables, including National Gas NTS public
  tariff rows and cross-border interconnector tariffs where available.
- Operator-owned local test price and contract records for price-dependent
  route economics.
- Web production build.
- Python API, contract, integration, security, unit, and workflow tests.

No full database URL, provider credential, `.env` content, or raw provider
payload was printed or committed.

## Runtime DB Evidence

- Alembic revision: `0011_reference_source_lineage`
- Missing required tables: `0`
- Runtime DB validator: passed
- App import: `app import ok`, `78` routes

PostgreSQL row counts after refresh:

- `tso_tariffs`: `1315`
- `market_observations`: `12`
- `fx_observations`: `6`
- `flow_observations`: `1000`
- `storage_observations`: `300`
- `lng_observations`: `300`
- `reference_nodes`: `788`
- `reference_tso_access_points`: `1000`
- `live_market_marks`: `2`
- `upstream_resource_contracts`: `1`

## Source Ingestion Evidence

Explicit source ingestion succeeded:

- ECB: `12` normalized FX-reference rows
- ENTSOG operational flow ingestion: `972` rows in the latest run, with `1000`
  flow rows present in PostgreSQL after merge
- ENTSOG reference network and TSO access: `2448` normalized rows
- GIE AGSI: `300` storage rows
- GIE ALSI: `300` LNG rows

Price/screen feeds were not live-called. EEX, ICE OCM, Trayport, Kpler,
Platts, ICIS, Argus, broker, weather, and LLM provider feeds remain gated by
customer credentials, entitlement, and source-specific operating rules.

## Runtime API Evidence

DB-backed API checks passed:

- `/api/health`: `200`
- `/api/route-cost/tso-tariffs`: tariff rows from runtime PostgreSQL
- `/api/market/fx`: `6` rows
- `/api/physical/flows`: `1000` rows
- `/api/storage/observations`: `300` rows
- `/api/lng/observations`: `300` rows
- `/api/reference-network/nodes`: `788` rows
- `/api/reference-network/tso-access`: `1000` rows

Route-cost live check:

- Scenario: explicit-leg European route, for example `GATE LNG -> TTF` or
  `TTF -> BBL -> NBP`
- Source: runtime PostgreSQL
- Status: `SUCCESS`
- Total cost: returned from stored route/tariff rows in the runtime DB

## Data Policy Result

Runtime/client fallback data was removed from the major V1 public surfaces:

- analysis/report snapshots no longer invent price, flow, capacity, route, or
  portfolio context without PostgreSQL.
- portfolio screen orders and PnL snapshots no longer return demo orders or
  demo PnL when the DB is missing.
- weather endpoints no longer return fixed city/temperature examples.
- workflow endpoints no longer return static route-cost/netback/backtest style
  results; they return an explicit `RUNTIME_DATA_REQUIRED` blocked payload.

Tests may still use test fixtures and source-shaped examples under `tests/`.

## Validation Commands Passed

```text
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
pytest -q tests/unit/test_route_cost_tariff_selection.py tests/unit/test_route_cost_tariff_models.py tests/api/test_route_cost_api.py tests/workflows
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
python scripts/ops/validate_v1_runtime_db.py --json
python scripts/ops/ingest_public_sources.py --source all --limit 1000 --json
```

Observed results:

- `ruff check .`: passed
- API/contract/integration/security tests: `326 passed`
- Route-cost and workflow focused tests: `47 passed`
- Web build: passed
- App import route count: `78`
- Runtime DB validator: passed

## Remaining Release Limitations

- Production scheduling, retry, monitoring, and alerting for source ingestion
  are not yet implemented.
- Commercial price/screen/vendor connectors remain gated until credentials and
  entitlement are configured and tested.
- Weather source ingestion remains a design surface; no live weather provider
  was called in this validation.
- LLM provider execution remains gated by backend-stored provider credentials
  and operator policy.
- Auth, audit depth, export governance, and multi-user entitlement enforcement
  still require production hardening.
