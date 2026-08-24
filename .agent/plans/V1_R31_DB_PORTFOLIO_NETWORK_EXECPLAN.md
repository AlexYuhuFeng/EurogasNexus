# R31: DB-Backed Portfolio Network Optimization ExecPlan

## 1. Goal

Connect the validated shared-capacity natural-gas flow optimizer
(`src/eurogas_nexus/optimization/network_flow.py`) to PostgreSQL-owned
commercial and infrastructure facts. A new public endpoint composes upstream
contracts, market-observation sale options, active route candidates, TSO
access posture, and effective tariffs by gas day/product into one
portfolio-level optimization. Every run persists its assembled inputs, source
references, assumptions, blockers, and contract-level PnL attribution as an
`optimization_runs` evidence row.

## 2. Non-goals

- No client-supplied network geometry, tariff, capacity, price, or volume for
  `RUNTIME_DECISION`; the existing sandbox endpoints remain unchanged.
- No trade execution, order entry, nomination submission, capacity booking,
  auto-trading, ETRM behavior, or approval action.
- No Kafka/Redis/streaming and no new optimizer/solver dependency.
- No new database migration. Existing tables are read; `optimization_runs`
  remains the only write.
- No R32 identity/SSO, R33 production source operations, R34 client
  workflows, or removal of `/api/workflows/*` in this increment.

## 3. Product boundary

The endpoint is a trader-reviewed daily portfolio optimization:
`POST /api/optimization/portfolio-network`. It accepts only a portfolio id,
gas day, capacity product, firmness, and a market-price age bound. It fails
closed (HTTP 422 with explicit blockers) when the PostgreSQL snapshot cannot
assemble authoritative inputs. Output is never executable and always carries
`human_review_required=True`.

## 4. Files to create/modify

Create:

- `src/eurogas_nexus/domain/route_cost/portfolio_network.py` — pure typed
  DB-composition and portfolio network optimizer contract.
- `tests/unit/test_portfolio_network_composition.py` — composition contract
  tests (missing/stale/incompatible facts, TSO/capacity/tariff gating).
- `tests/optimization/test_portfolio_network_optimizer.py` — attribution,
  shared capacity, rerouting, and validation tests.
- `tests/api/test_portfolio_network_api.py` — DB-backed API tests with SQLite.
- `tests/sdk/test_portfolio_network_client.py` — SDK parity tests.
- `docs/operations/PORTFOLIO_NETWORK_OPTIMIZATION.md` — bilingual operator
  runbook (English section + Chinese companion inline or `-CN` file as repo
  convention allows).

Modify:

- `src/eurogas_nexus/optimization/network_flow.py` — expose final supply
  usage and demand service plus stable supply/demand ids for decomposition.
- `src/eurogas_nexus/api/routes/public/optimization.py` — add the new
  DB-only endpoint and extend run persistence source refs.
- `src/eurogas_nexus/sdk/optimization.py` — add SDK DTO and method.
- `tests/contract/test_api_surface_stability.py` — pin the new path.
- `tests/contract/test_architecture_alignment.py` — update route count and
  R31 queue assertions.
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md` and `-CN.md` — mark R31
  complete with delivered scope and evidence.
- `docs/architecture/CURRENT_PAUSE_POINT.md` and `-CN.md` — route count and
  optimization state.
- `docs/architecture/PHASE_TWO_OPTIMIZATION.md` and `-CN.md` — expose the
  new DB-backed capability status.
- `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md` and `-CN.md` — record
  the additive path and its declared consumers.

## 5. Dependency policy

Python standard library, FastAPI/Pydantic, SQLAlchemy, and the existing
optimization/route-cost domain modules only. No new Python or client
dependencies.

## 6. Data policy

All authoritative inputs come from PostgreSQL tables:

- `upstream_resource_contracts` → supply resources;
- `route_candidates` → route topology, TSO requirements, and route-level
  available capacity;
- `tso_tariffs` → effective tariffs selected by point/Tso/direction/gas
  year/product;
- `company_tso_access` → company access posture (ACTIVE/CONFIRMED passes,
  DENIED/INACTIVE/SUSPENDED blocks; missing access blocks required TSOs);
- `reference_nodes` → canonical node ids for contract and route endpoints;
- `market_observations` + `fx_observations` → sale prices converted to
  GBP/MWh as-of gas day.

Tests use small synthetic SQLite rows marked `test_fixture:not_customer_data`.
No live provider or customer data is used. Trial/release never falls back to
local files; missing DB or blocked composition returns 503/422.

## 7. API impact

Additive-only public path:

```text
POST /api/optimization/portfolio-network
```

Request accepts only decision metadata. Response is the standard
`data`/`meta` envelope; `meta` adds lineage, assumptions, `run_id`, and
`snapshot_id`. The path is declared in the pinned surface gate and the
contract-evolution policy.

## 8. DB impact

No migration. Reads the existing tables above and appends immutable
`optimization_runs` rows (`optimization_type="portfolio_network"`,
`decision_context="RUNTIME_DECISION"`). Importing the app/API still opens no
socket or database connection.

## 9. Tests

- Composition: contract required for every sale route; missing node, missing
  market price, stale market price, missing FX, missing tariff, unsupported
  tariff unit, missing/denied TSO access, missing route capacity, and local
  sale all behave explicitly.
- Optimizer: shared route capacity across two resources, alternate reroute
  when cheap capacity is exhausted, local/other-market comparison, negative
  margin not served, deterministic order, conservation, and contract-level
  PnL sums to portfolio objective.
- API: DB snapshot success persists evidence; no DB returns 503; blocked
  snapshot returns 422 with blocker codes; client inputs cannot be supplied.
- SDK: new method sends only decision metadata and parses the DTO.
- Contract: pinned path set and documented route count updated.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/unit/test_portfolio_network_composition.py tests/optimization/test_portfolio_network_optimizer.py tests/api/test_portfolio_network_api.py tests/sdk/test_portfolio_network_client.py tests/contract/test_api_surface_stability.py tests/contract/test_architecture_alignment.py
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
```

## 11. Acceptance criteria

1. No client-provided network geometry, tariff, capacity, or market price is
   authoritative for `RUNTIME_DECISION`.
2. Missing, stale, or incompatible facts produce explicit blocker codes or
   warnings; blocked compositions never run the optimizer.
3. Shared route capacity and TSO access are enforced across the portfolio by
   the residual network-flow model.
4. Contract-level PnL attribution is reconstructed from final flows and sums
   to the portfolio objective.
5. Source ids, observation times, freshness, quality, assumptions, blockers,
   and `run_id` are preserved in the response and `optimization_runs`.
6. API, SDK, integration, optimization, and contract tests pass.

## 12. Rollback notes

Revert the focused commit. No migration rollback is needed. The new endpoint
is additive; the pinned path gate must be reverted with it. Existing sandbox
optimization endpoints and the network-flow module remain unchanged in their
previous external behavior (the module gains optional result fields only).
