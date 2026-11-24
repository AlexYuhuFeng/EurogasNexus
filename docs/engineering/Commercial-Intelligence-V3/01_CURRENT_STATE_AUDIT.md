# 01 Current state audit

Evidence before implementation: each statement below names the code it rests on. Where the
audit could not verify behaviour by test, it says so. Paths are under `src/eurogas_nexus/`
unless they start with a top-level directory.

## Repository baseline (2026-11-24)

| Item | Value |
| --- | --- |
| Baseline | `main` at `6d21b898661d6466418b3aaeab505a7bc4fb4013` ("CI: pin runners to ubuntu-24.04; ...") |
| Programme branch | `innovation/continuous-commercial-intelligence`, created from the baseline; ancestry `main@6d21b89 -> innovation/...` |
| Remote branches | `main`; `claude/gas-trading-tool-review-08bgpo` (same commit as `main`). No release branches. No active architecture branch on the remote (the `today-gas-day` branch named in the execution state was never pushed). |
| Tags | 57: `v0.5-preview-*`, `v0.6.0-rc.1`, `v0.6.0-rc.2`, `v0.7.0-rc.1`, `v0.8.0-rc.1` to `rc.3`. None touched. |
| Uncommitted user changes | None: the work started from a fresh clone, so there was nothing to preserve. |
| Schema head at baseline | `0076_gas_day_nominations` (now `0077_market_event_outbox` on the branch). |
| Baseline tests | Recorded in [09_VALIDATION_EVIDENCE.md](09_VALIDATION_EVIDENCE.md). |

Why `main` is the baseline: it is the only maintained line, CI runs on it, every release
candidate tag was cut from it, and no release or architecture branch exists to protect.

## Capability assessments

### 1. Continuous market intelligence

- **Implementation.** Scheduled ingestion through `scripts/ops/run_dataops_scheduler.py`
  and `domain/dataops` (schedule, retry, circuit, run status). Real public connectors under
  `ingestion/`: GIE (AGSI/ALSI, IIP, transport), ENTSOG (flows, tariffs, UMM), ECB, ENTSO-E,
  Elexon, EIA, ECMWF open data, EEX public NGP, National Gas. Change reached analysis only
  through `application/opportunities/schedule.py` (CP-13): eleven input classes flagged
  dirty, one debounced full evaluation after five minutes.
- **Limitations and debt (before M4).** No event identity, revision chain or replay at
  event level. `affected_by` and `OutboxSubscription` were never called; the `outbox`
  evaluation trigger was never produced. `run_due` reads then deletes the pending flags
  without a lock, so a change noted between the two is lost. The debounce is per process
  and does not hold across replicas. Manual importers do not note changes. Prices and FX
  are overwritten in place; physical observations do keep revisions
  (`observation_revisions`, migrations 0062/0063) and REMIT keeps message versions.
- **Since M4.** See [09_VALIDATION_EVIDENCE.md](09_VALIDATION_EVIDENCE.md): canonical
  events, outbox, targeted re-evaluation, replay and staleness exist and are tested.

### 2. Ontology

- **Implementation.** `domain/ontology` (concepts, relations, constraints, identity,
  source identity, currency, quantity, timebase, markets, Turtle export), identity
  quarantine in `application/identity_resolution.py`, ADR Decisions 25 and 27.
- **Limitations.** Three overlapping ontologies with different concept sets: the
  executable one (`domain/ontology`), the GRM OWL export, and the research
  `energy-ontology/v1` (`domain/research/ontology.py`); `docs/ontology/ONTOLOGY_AUTHORITY.md`
  documents the split. `bindings.py` binds about 20 concepts to tables. No counterparty
  entity. Relations are code tuples, not navigable instance links (by design, Decision 25).

### 3. Digital twin

- **Implementation.** NWE reference network (318 nodes, 360 edges, schematic),
  `domain/fundamentals` (balance, forward balance, storage history), REMIT outages
  (`application/remit_outages.py`), capacity resolution.
- **Limitations.** No pipeline hydraulics. Capacity net of outages is computed but not
  consumed by the optimisers. `ingestion/connectors/*` (trayport, ice_ocm, eex, ...) are
  mock shells next to the real ingestion modules.

### 4. Probabilistic forecasting

- **Implementation.** Three demand models (GB demand, the NWE functional model, ECMWF
  regional demand under RFC-0003). The NWE functional model has a split-conformal interval.
- **Limitations.** NumPy is absent from `requirements-runtime.lock` and
  `requirements.lock` (only `requirements-scientific-ci.lock` has it), so in a shipped image
  the RFC-0003 fitter raises `MissingNumpyError`. No ensemble or quantile forecasts and no
  CRPS scoring.

### 5. Contract modelling

- **Implementation.** `domain/contracts` (kinds, price terms), contract revisions,
  payment terms, tariffs, valuation snapshots (`domain/valuation`), LNG cargo economics.
- **Limitations.** Take-or-pay (ACQ, make-up, carry-forward) is not modelled. LNG
  economics exists three times (`domain/lng/cargo_economics.py`,
  `domain/research/lng_cargo_economics.py`, `domain/portfolio/lng_bid.py`), and
  `domain/route_cost/lng_terminal_reference.py` is imported only by tests.

### 6. Portfolio and asset optimisation

- **Implementation.** `optimization/` with in-house pure-Python solvers: route, storage,
  capacity, nomination, contract, joint. Three independent min-cost-flow kernels
  (`optimization/network_flow.py`, `optimization/circulation.py`,
  `domain/route_cost/resource_pool.py`) and two resource-pool engines. The circulation
  kernel is checked against HiGHS in a test that skips without SciPy.
- **Limitations.** The joint optimiser is experimental. Storage dynamic programming has no
  bound on state size. No hedge optimisation. No LP/MIP backend.

### 7. Event-driven decisions

- **Implementation.** The opportunity engine (`domain/opportunities`, evaluators
  hedge_gap, sell_down, event_exposure, held_capacity, locational, market_scan, reroute,
  storage_spread; lifecycle, claims, ranking), well tested. Notifications outbox
  (`application/notifications.py`).
- **Limitations.** The legacy `scan_and_persist_intraday_opportunities`
  (`db/repositories/market_intelligence.py`) still feeds
  `/api/stream/opportunities` and alerts; new-engine opportunities raise no alert.
  Notification dispatch takes no row lock and sends email only.

### 8. Interoperability

- **Implementation.** Python SDK and CLI (`packages/python-sdk`, `cli/`), signed (HMAC)
  handoff packages, public API under `/api`.
- **Limitations.** No committed OpenAPI document. Federation (`domain/federation`) is a
  contract shell. Licensed vendors (Trayport, ICE, EEX licensed, Platts, Argus, Kpler) are
  shells or simulators. The HMAC handoff has two tests.

### 9. Governed AI

- **Implementation.** LLM narrative with grounding (`application/grounding.py`), audit and
  RBAC; provider abstraction in `llm/`. Agent runtime (`application/agents`).
- **Limitations.** The agent runtime is deferred behind a flag. MCP (`mcp/server.py`) is
  development only and carries no user identity. No token metering.

### 10. Resilience

- **Implementation.** Health and readiness endpoints, dataops retry and circuit breaker
  (`domain/dataops/retry.py`), pipeline health.
- **Limitations.** Backups are manual, no point-in-time recovery. No stale-source or
  heartbeat alerting. `data_quality/` is a contract shell. Five freshness implementations
  (`domain/monitoring/freshness.py`, `domain/dataops/freshness.py`,
  `application/freshness_contract.py`, `application/projections/freshness.py`,
  `runtime_store.FreshnessState`). Scheduler subprocesses have no timeout.

### 11. Deployment

- **Implementation.** Docker image, release pipeline, OIDC sign-in, desktop (Tauri) shell.
- **Limitations.** No multi-tenancy. Portfolio isolation is off by default with two tests.
  `infra/` holds placeholders. Desktop builds may be unsigned.

### 12. Value attribution

- **Implementation.** Backtest engine (`domain/backtest`) with temporal guards.
- **Limitations.** No realised-value or outcome ledger linking recommendation, trade and
  mark-to-market. At least five overlapping P&L engines: the backtest engine, strategy_lab,
  spread analysis / intraday strategy, research backtest and the frozen-weather
  `evaluate_shadow`.
