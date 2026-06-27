# R3: Reference Network and Relationship Mapping Report

**Milestone ID:** R3
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- 6 DB models created: ReferenceNode, ReferenceEdge, ReferenceFacility,
  ReferenceMarketHub, NodeFacilityMapping, TopologyMarketMapping.
- Alembic migration `0003_r3_reference_network` creates all 6 tables.
- Required table registry updated with all 6 reference network tables.
- 7 read-only API routes under `/api/reference-network/` serving synthetic
  fixture data: /nodes, /nodes/{id}, /edges, /edges/{id}, /facilities,
  /facilities/{id}, /market-hubs.
- All responses include research metadata envelope: research_only,
  human_review_required, source_references, warnings.
- Mapping tables (NodeFacilityMapping, TopologyMarketMapping) include confidence
  (float 0.0-1.0) and eligibility (str) fields.
- Synthetic fixture data only 鈥?12 nodes, 10 edges, 7 facilities, 7 market hubs.
- No real ENTSOG/GIE/vendor data committed.
- Geometry is map display only; market relevance requires explicit mapping.
- App import remains DB-free (14 routes now: 7 health/compat + 7 ref-network).
- Default tests remain DB-free.

## Files Created / Modified

- `src/eurogas_nexus/db/models/reference_network.py` 鈥?6 SQLAlchemy models
- `src/eurogas_nexus/db/models/__init__.py` 鈥?Updated exports
- `src/eurogas_nexus/db/repositories/reference_network.py` 鈥?DTOs, protocols,
  and SQLAlchemy adapter classes
- `src/eurogas_nexus/api/routes/public/reference_network.py` 鈥?7 read-only API
  routes with synthetic fixtures
- `src/eurogas_nexus/api/route_registration.py` 鈥?Registered reference network
  router
- `src/eurogas_nexus/db/registry.py` 鈥?Added 6 reference network tables
- `alembic/versions/0003_r3_reference_network.py` 鈥?New migration
- `.agent/plans/V1_R3_REFERENCE_NETWORK_EXECPLAN.md` 鈥?ExecPlan
- `data/release_v1/r3_reference_network_report.md` 鈥?This report
- `tests/contract/test_reference_network_models.py` 鈥?Model contract tests (10)
- `tests/api/test_reference_network_api.py` 鈥?API contract tests (16)

## DB Impact

New tables: reference_nodes, reference_edges, reference_facilities,
reference_market_hubs, node_facility_mappings, topology_market_mappings.
New Alembic revision: 0003_r3_reference_network (down_revision:
0002_m4_create_ingestion_runs).

## API Impact

7 new read-only routes under `/api/reference-network/`.

Route count: 7 鈫?14.

## Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Result:
- ruff: All checks passed
- pytest: 158 passed (was 132 before R3; +26 new tests)
- app: import ok, 14 routes

## Next Milestone

R4: Source Registry and Ingestion Control Plane
