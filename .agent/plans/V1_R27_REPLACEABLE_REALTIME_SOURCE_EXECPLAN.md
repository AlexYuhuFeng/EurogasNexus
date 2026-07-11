# V1 R27 Replaceable Real-Time Source ExecPlan

## 1. Goal

Make simulated commercial market feeds operational substitutes for licensed feeds
without creating a second workflow. EEX, ICE OCM, and Trayport-shaped simulation
must write the same canonical PostgreSQL records consumed by the API, SDK, route
economics, strategy evaluation, and clients. Separately document the authoritative
boundary for European network topology and pipeline geometry. Redesign the capacity
workspace around a trader's point-level flow, headroom, TSO-product, tariff, storage,
and LNG inspection workflow.

## 2. Non-goals

- No live commercial connector call or credential use.
- No trade execution, order submission, or nomination submission.
- No claim that ENTSOG or GIE alone supplies surveyed pipeline centerlines.
- No client-side market, topology, or geometry fixture.

## 3. Product boundary

Simulation is a source adapter used before commercial entitlement is available. It
must preserve timestamps, cadence, provenance, ingestion status, canonical storage,
and all downstream workflows. Licensed connector status remains visible and distinct
from effective workflow readiness.

## 4. Files to create/modify

- `.agent/plans/V1_R27_REPLACEABLE_REALTIME_SOURCE_EXECPLAN.md`
- `src/eurogas_nexus/ingestion/simulated_market_prices.py`
- `src/eurogas_nexus/api/routes/public/sources.py`
- `scripts/ops/ingest_simulated_market_prices.py`
- `scripts/ops/seed_preview_runtime_data.py`
- `clients/web/src/api/client.ts`
- `clients/web/src/app/workspaceDerivedData.ts`
- `clients/web/src/components/SourceCenter.tsx`
- `clients/web/src/components/CapacityWorkspace.tsx`
- `clients/web/src/components/GasNetworkMap.tsx`
- `clients/web/src/components/NetworkWorkspace.tsx`
- `clients/web/src/components/ResourcePoolPathOverlay.tsx`
- `clients/web/src/i18n/en.json`
- `clients/web/src/i18n/zh.json`
- `clients/web/src/styles/app.css`
- `docs/operations/SIMULATED_MARKET_PRICE_SOURCES.md`
- `docs/architecture/EUROPEAN_NETWORK_GEOMETRY_POLICY.md`
- focused API, ingestion, and client contract tests

## 5. Dependency policy

Use the existing Python, SQLAlchemy, FastAPI, React, and TypeScript stack. Add no
dependency.

## 6. Data policy

- PostgreSQL remains the source of truth.
- Every simulated row is visibly marked and source-attributed.
- EEX, ICE OCM, and Trayport simulation uses incremental market cadence.
- Replacing simulation with a licensed adapter must not change downstream contracts.
- Official topology and operational observations remain separate from geometry.

## 7. API impact

Extend source records with non-breaking operational fields: `operational_status`,
`workflow_ready`, `effective_source_system`, `effective_record_count`, and
`effective_last_success_at_utc`. Preserve native `connectivity_status` and credential
state for entitlement truth.

## 8. DB impact

No migration. `Trayport_Sim` writes to the existing `market_observations` and
`ingestion_runs` tables.

## 9. Tests

- Simulated Trayport rows use the canonical runtime tables and realtime cadence.
- Licensed sources retain native credential status while reporting simulated
  operational readiness.
- Source posture does not count an active substitute as a blocked workflow.
- Client types, source sorting, status labels, and actions use operational status.
- Documentation contract states the geometry verification boundary.
- Capacity controls, pagination, status thresholds, and point inspection remain
  functional in English, Mandarin, light mode, and dark mode.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api/test_sources_api.py tests/ingestion/test_simulated_market_prices.py tests/contract/test_workspace_derived_data_contract.py tests/contract/test_client_release_surface.py
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- Trayport simulation follows PostgreSQL -> API -> client like licensed data.
- Source Center distinguishes licensed connector status from effective workflow status.
- Route, strategy, PnL, and market workflows can continue on labelled simulation.
- Switching to licensed data requires adapter/credential configuration, not workflow
  rewrites.
- ENTSOG/GIE topology and operational capabilities are documented accurately.
- Unverified route-candidate geometry is never represented as official pipeline shape.
- The capacity workspace distinguishes public capacity/product observations from
  company-specific TSO contractual access.

## 12. Rollback notes

Remove the additional simulated source and operational fields. No schema rollback is
required; existing simulated rows remain identifiable through `source_system` and
`metadata_json.simulated`.
