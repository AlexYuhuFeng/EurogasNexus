# V1 R3 Reference Network and Relationship Mapping ExecPlan

## 1. Goal

Create the canonical reference network domain slice: DB models for nodes, edges,
facilities, and market hubs; explicit topology-market mapping tables with
confidence/eligibility; read-only `/api/v1/reference-network/*` routes; and
synthetic European gas network fixtures. All data is synthetic — no real vendor
or operator data is committed.

## Internet Requirement

Internet required: no

Reason: This milestone uses local Python code, SQLAlchemy models, synthetic
fixtures, and local tests. No external documentation or live service is required.

Fallback if offline: Not needed.

## 2. Non-goals

- No real ENTSOG, GIE, or vendor data committed.
- No live market prices, flows, capacity, or outage data.
- No route cost, netback, feasibility, or allocation workflows.
- No frontend, desktop, Node, Rust, Kafka, Redis, Celery work.
- No map rendering (geometric data is lat/lon only — map rendering is a web
  client concern).
- No commercial connectivity implications from geometry alone.

## 3. Product boundary

This milestone adds the first product-shaped domain slice: a read-only reference
network with explicit topology-market mappings. Geometry is map display only
until mapped. Market relevance requires explicit mapping with confidence and
eligibility fields. All data is synthetic.

## 4. Files to create/modify

### New models
- `src/eurogas_nexus/db/models/reference_network.py` — ReferenceNode, ReferenceEdge,
  ReferenceFacility, ReferenceMarketHub, NodeFacilityMapping, TopologyMarketMapping

### New repositories
- `src/eurogas_nexus/db/repositories/reference_network.py` — typed read-only
  repository implementations

### New API routes
- `src/eurogas_nexus/api/routes/v1/reference_network.py` — read-only routes:
  GET /nodes, /nodes/{id}, /edges, /edges/{id}, /facilities, /facilities/{id},
  /market-hubs

### New fixtures
- `data/fixtures/reference_network_fixture.json` — synthetic European gas
  reference points (10-15 nodes, connecting edges, 5-7 facilities, 5-7 market hubs)

### Migration
- `alembic/versions/0003_r3_reference_network.py` — DDL for reference network tables

### Updated files
- `src/eurogas_nexus/db/models/__init__.py` — export new models
- `src/eurogas_nexus/db/registry.py` — add reference network tables to REQUIRED_TABLES
- `src/eurogas_nexus/api/routes/v1/router.py` — include reference network router
- `docs/contracts/04_DB_CONTRACT.md` — update for R3
- `data/release_v1/r3_reference_network_report.md` — milestone report

### Tests
- `tests/contract/test_reference_network_models.py` — model contract tests
- `tests/api/test_reference_network_api.py` — API contract tests (DB-free with mocks)
- `tests/integration/test_reference_network_db.py` — DB integration tests (optional live)

## 5. Dependency policy

No new dependencies. SQLAlchemy models, FastAPI routes, Pydantic schemas only.

## 6. Data policy

Synthetic fixtures only. No real vendor data committed. Geometry is explicitly
labeled as synthetic. Source references in API responses mark data as synthetic.

## 7. API impact

New read-only routes under `/api/v1/reference-network/`:
- `GET /nodes` — list with optional country/type filters
- `GET /nodes/{id}` — single node detail
- `GET /edges` — list with optional from/to node filters
- `GET /edges/{id}` — single edge detail
- `GET /facilities` — list with optional type/country filters
- `GET /facilities/{id}` — single facility detail
- `GET /market-hubs` — list market hubs

All responses include research metadata (research_only, human_review_required,
source_references, warnings).

## 8. DB impact

New tables:
- `reference_nodes` — id, name, node_type, country, lat, lon, metadata JSON
- `reference_edges` — id, from_node_id, to_node_id, edge_type, metadata JSON
- `reference_facilities` — id, name, facility_type, country, lat, lon, metadata JSON
- `reference_market_hubs` — id, name, hub_code, country, metadata JSON
- `node_facility_mappings` — id, node_id, facility_id, confidence float, eligibility str
- `topology_market_mappings` — id, node_id, market_hub_id, confidence float, eligibility str

New Alembic revision: `0003_r3_reference_network`

Required table registry updated to include all 6 new tables.

## 9. Tests

Required tests:
- Models are importable and have correct table names.
- API routes return 200 with synthetic data (mocked repositories).
- API routes return research metadata in responses.
- API routes return 404 for unknown IDs.
- Mapping tables include confidence (0.0-1.0) and eligibility fields.
- No real vendor data in fixtures.
- App import remains DB-free.
- Default tests remain DB-free.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/contract/test_reference_network_models.py tests/api/test_reference_network_api.py
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- Reference network models exist with correct table names.
- Alembic migration creates all 6 tables.
- API routes serve synthetic fixture data through repositories.
- All responses include research metadata.
- Mapping tables carry confidence (float) and eligibility (str) fields.
- No real ENTSOG/GIE/vendor data committed.
- Geometry does not imply commercial connectivity.
- Market relevance requires explicit mapping.
- App import DB-connection free.
- Default tests DB-free.
- Targeted validation passes.

## 12. Rollback notes

Revert the new models, repositories, API routes, fixture file, Alembic migration,
and milestone report. Remove tables from required table registry. DB rollback:
`alembic downgrade 0002_m4_create_ingestion_runs` if migration was applied.
