# Backend and architecture audit, 2026-11-26

Scope: the FastAPI/SQLAlchemy/Alembic backend (`src/eurogas_nexus`), the ingestion scripts
(`scripts/ops`), the demo start-up (`scripts/demo`) and what the web client receives. Branch
`backend-audit` from `74aec00`. For each finding: what was seen, how it arose, the other places
with the same cause, the fix (or the proposal) and its priority. Every fix has a test.

Evidence used: the live demo's API log and job tables (read only, 2026-11-26, container up 2 h,
build `6621f46`); a probe of every GET route without a path parameter against an app with no
database; the same probe on PostgreSQL 16 with the demo desk seeded
(`scripts/ops/api_consistency_audit.py` plus a per-route statement counter); static scans of the
source.

## Findings

Priority: **H** wrong or misleading answers, or a failure loop; **M** inconsistency a customer or
integrator meets, or a measured hot spot; **L** hygiene.

| ID | Finding | Cause | Other occurrences | Fix / proposal | P | Status |
|----|---------|-------|-------------------|----------------|---|--------|
| L1 | Demo: the GIE IIP catch-up read 7 pages in 1,841 s, was refused (`iip_upstream_refused`) and logged as failed every round | A partial read that stored the newest messages counted as a failed step, so the step's window stayed at its 30-day maximum and every round re-read the same newest pages into the same rate limit (a self-sustaining loop) | Any catch-up step whose source rate-limits long reads | `ingest_remit_iip.py` reports `read_back_to`; the demo counts a partial read that stored rows as the step's round and logs the part of the window not read (`run_catch_up_step` → `"partial"`, audit detail `partial=`) | H | Fixed |
| L2 | The production scheduler recorded every failed ingest script as `INTERNAL` | The script contract carried failure codes (`iip_rate_limited`, HTTP status) but `run_dataops_scheduler` only looked at the exit code; the retry/circuit policy (`domain/dataops/retry.py`) never saw RATE_LIMITED or PROVIDER_UNAVAILABLE from a script | All 11 script-backed sources (`_SCRIPT_COMMANDS`) | `classify_script_failure()` maps the report's codes to `FailureCategory`; rows a failed script stored are counted; EIA reports `eia_http_502`, `eia_timeout`, `eia_no_prices` | H | Fixed |
| L3 | Demo: every hourly monitoring scan printed `degraded … service_principal_not_configured` | The demo enables the model provider by default but provisions no `EUROGAS_NEXUS_WORKER_PRINCIPAL`; the scan asked for enrichment it could not be granted | — | Enrichment is requested only when provider and service identity are both set | M | Fixed |
| L4 | Demo log: 404s for `/api/stream/live` (102), `/api/me/alert-state` (55), `/api/pricing/source-precedence`, `/api/capacity/bookings`, `/api/map/situation`, `/api/health/version` | A client newer than the server (the demo runs `6621f46`; the served bundle does not call these, so the caller is another client build) | Any customer with desktop and server on different releases | Proposal: a version handshake (`/api/health` already reports the build; the client should compare its route census and degrade a missing route to "not on this server" instead of polling it) | M | Proposal |
| L5 | Demo container logs reach back only to the last container start (2 h) | `docker compose` default log driver, recreated on each deploy | Customer runtime compose | Proposal: `logging: {driver: json-file, options: {max-size, max-file}}` or the host journal, so a reviewer can read the previous day | L | Proposal |
| A1 | A path no route matches, or a wrong method, answered a bare `{"detail": "Not Found"}` | Starlette raises its own `HTTPException`; only FastAPI's subclass had the envelope handler | The web-client static fallback built its own `{detail:{error,message}}`; `origin_csrf` built its own body | One `error_body()` used by every handler and both middlewares; router 404/405 enveloped | H | Fixed |
| A2 | 82 refusals sent English text with no code; the client could not translate them | `HTTPException(404, f"…")` was the path of least resistance and nothing stopped it | `strategy_registry` (22), `shadow` (12), `source_operations` (9), `research_data` (8), `agents` (5), `storage` (5) and 13 more modules | `api.errors.ApiError(status, code, text, params=…)`; 73 sites converted (the rest were dicts already); the envelope carries `params` and `fallback_message` beside the code; `detail` is unchanged. Gate: `tests/contract/test_api_error_codes.py` | H | Fixed |
| A2b | An uncatalogued code (`personal_keys_are_for_people`) reached the client as `UNCLASSIFIED_ERROR` | The taxonomy fell back to SYSTEM when the code's name implied no family, discarding the code the client translates by | Every endpoint code without a family word | The HTTP status supplies the family and the recoverability (a 403 is AUTH, a 404 permanent); the code keeps its name | M | Fixed |
| A2c | Three spellings of the code key (`error`, `code`, `error_code`) and four of "needs the runtime database" | Per-module conventions | `runtime_db_not_configured`, `runtime_database_not_configured`, `runtime_database_required` beside the catalogued `runtime_db_required` | The handler reads all three keys; `CODE_ALIASES` report the catalogued code | M | Fixed |
| A2d | User-facing English in success payloads: 29 `warnings=[…]` sentence literals at route call sites (`market` 10, `tariffs` 6, `physical` 3, `contracts` 3 …), about 94 `message`/`reason`/`note` sentence fields in payloads | `_env(…, warnings=[str])`: ten hand-written envelope helpers take a list of strings | `research_data._env`, `market._env`, `physical._env`, `access._env`, `jobs._env`, `review._env` … | Proposal: a `Notice(code, text, params)` accepted by one shared envelope builder, emitted as `meta.notices` beside the existing `meta.warnings` (kept as the fallback text), then migrate module by module. Not done here: it touches every route module the other branches are editing | M | Proposal |
| A3 | A read with no runtime database answered in four ways: empty + English warning, empty + code warning, empty + nothing (`/api/portfolio/books`, `/api/portfolio/map-situation`, `/api/research/spread-series`, `/api/route-cost/tariff-publications`), or 503 under four codes | Each route decided for itself; an empty outage list with no warning reads as "no outages" | 56 reads answer 200 empty, 32 answer 503 | One rule: every enveloped `/api/` read answered without a store carries `meta.runtime_store = {state: not_configured, code: runtime_db_required}` (middleware, so no route can forget it); refusals use the catalogued code | M | Fixed |
| A3b | `/api/strategies`, `/api/strategy-runs`, `/api/shadow-*` answer `runtime_db_unavailable` (retry) when no store is configured (configure) | `_db_unavailable` used for both cases | `backtest-experiments` | `runtime_db_required` when no store is configured (strategy registry, shadow) | L | Fixed |
| A4 | Calculation inputs read with `.limit(N).all()` stopped silently past the bound; some reads were unordered (an arbitrary part) or ascending (the **newest** marks dropped) | A memory guard written without an overflow signal | `position_inputs.curve_quotes` (ascending, 20k), `desk_today` storage (unordered, 40k), `fundamentals` NWE prices (unordered, 50k), report LNG (60k) and power burn (400k), `remit_outages` open messages (unordered DISTINCT, 5k: outages left out of the list and the map), `news_ingest._latest_remit` (unordered 20k: a message's "latest" could be an older version) | `application/bounded_reads.read_bounded()` reads one past the bound and raises `ReadBoundExceeded`, answered 422 `read_bound_exceeded` with `params {what, bound}` | H | Fixed |
| A4b | Newest-first reads with a bound (`map_situation` flows 20k, `map_assets` capacity 20k / stock 5k, `analysis` 20–50, `support` reports 500, `streaming` pages) drop the oldest rows silently | Same cause, lower harm (the newest per key is what they want) | — | Proposal: `read_bounded` where the result is a list shown to the user (`support` reports: page with `meta.next_cursor`) | M | Proposal |
| A4c | `GET /api/market/observations` returned the whole table: 20.8 MB, 2.3 s on the demo desk | "Deliberately unbounded" export read | `/api/market/fx` (whole table), `/api/market/quotes` (stopped at `limit` silently) | One keyset style (`application/keyset_paging.py`, the audit cursor made general): `limit` (default 1,000), `cursor`, `from_utc`/`to_utc`, `meta.continuation`; CSV pages in headers; SDK reads a range page by page; CLI/MCP read seven days; web FX reads ten days | M | Fixed |
| A5 | Pagination: four styles (`limit` 33 routes, `cursor+limit` 2, `limit+offset` 2, `after+limit` 1) | Grown per route | — | Proposal: `limit` + opaque `cursor`, `meta.limit`, `meta.next_cursor`, `meta.truncated` on every list | L | Proposal |
| A6 | Permissions | Checked: the route-permission registry is central (`security/permissions.py`, 500 on an undeclared path); work mode is derived from capabilities (`available_work_modes`) and `work_mode_grants_authority` is reported false; no route grants by persona (rule 7 holds) | `db/repositories/strategy_access.py` raises HTTP errors from the data layer | Its two refusals now carry codes; proposal: a domain `AccessDenied` mapped at the API edge | L | Partly fixed |
| O1 | "Is this row simulated?" had five rules in ~50 places: `endswith("_Sim")` (most), that or `metadata.simulated`, a case-insensitive suffix, or suffix or a `demo` prefix | No shared predicate; each reader wrote its own | 39 hand-written suffix checks remain | `domain/ontology/provenance.is_simulated()`: metadata flag, `*_Sim` any case, or the demo desk's `DEMO` source; the five named helpers delegate to it; a ratchet test stops new hand checks; market observation rows carry `simulated` | H | Fixed (ratchet) |
| O1b | Provenance dropped between store and API: the demo desk's fictional REMIT messages (`source_system = DEMO`) were listed as `REMIT` with no sign they were invented (rule 17) | `UmmMessage` had no `source_system`, so `remit_outages` lost it rebuilding messages from rows | Map situation and reports read the same outage rows | `UmmMessage.source_system`; outage rows carry `simulated` (the entitlement family stays `REMIT`) | H | Fixed |
| O2 | `capacity_impact_mcm_d` was `mcm_d or 0.0`: an outage published in GWh/d read as removing 0 mcm/d | A legacy float field with a zero default (`OutageEvent`, the SDK) | SDK `OutageEvent.capacity_impact_mcm_d = 0.0` | `None` when unknown; SDK type `float | None`. The client type `number` must become `number | null` (UI owners) | M | Fixed (backend, SDK) |
| O3 | A GIE record with no `gasDayStart` would have been stamped with the server's calendar date | `_gas_day_period` fallback `or date.today()` (latent: both callers skip such records) | `public_sources.py:931`; `date.today()` in 6 other places (access validity, position FX table date) | Fallback removed (raises) | L | Fixed |
| O4 | Hub identity duplicated (aliases, case, quote currency) | — | Branch `hubid` unifies it (ETF/GTF, VTP/CEGH, migration 0091) | Not touched here | M | Other branch |
| O5 | Money and price fields with no unit or currency beside them | Payload shapes grown per screen | `desk/today` series `value`, `forward-balance` `price`, `daily-balance` `cash_out_cost`, `position-ladder` `mark`/`mark_to_market`, `spreads/board` `cost`/`value`, `upstream-contracts` `credit_support_amount` (from the consistency audit) | Proposal: add `unit`/`currency` siblings (additive) | M | Proposal |
| O6 | Time-named keys holding non-times: `largest_at: "NBP 2027-01"`, `marked_at: "current mid"`, `as_of: "2025-12"`, `daily_at: "08:15"` | Naming | `discoveries`, `mandate-usage`, `market/prompt`, `forward-balance`, `sources` | Proposal: rename additively (`largest_contract`, `mark_basis`, `as_of_month`, `daily_at_local`) | L | Proposal |
| O7 | Rule 19: which inputs were entered by hand | Each calculation said it its own way (`inputs: ["manual"]`, `basis: "entered"`, "entered by hand" texts) or not at all | Every calculation route | One field `meta.manual_inputs: [{name, value, unit, entered_by, entered_at}]`, empty when all inputs came from records; builder `application/manual_inputs.py`, one-line decorator `api/manual_inputs.states_manual_inputs`; client `components/ui/ManualInputsNote.tsx`. Inventory below | M | Fixed (wired routes listed) |
| O8 | Ingestion run status vocabulary mixed (`succeeded` vs `SUCCEEDED_WITH_WARNINGS`) | The simulated-price writer and the scheduler write different spellings | Normalised at read (`domain/dataops/run_status.py`) | Proposal: write the enum value | L | Proposal |
| I1 | Each ingest script hand-rolls its HTTP retry | Scripts written one source at a time | `ingest_eia._read_with_retry`, `gie_iip.http_page_getter`, `national_gas_rest`, `national_gas_demand` | Proposal: one bounded retry helper in `core/outbound_http` (Retry-After, capped back-off, refusal envelope hook) | M | Proposal |
| I2 | Freshness | Checked: GIE AGSI/ALSI rounds read the newest page within the operator budget and are recorded `SUCCEEDED_WITH_WARNINGS` with `complete=false;stop=operator_record_budget`; freshness is the newest gas day held, which is honest | — | — | — | OK |
| P1 | `/api/research/spreads/board` read the quote table 54 times (3.7 s); LNG cargo economics the same | A price book opened per price input (hub, period, side) in `LiveSnapshotReader._load_price` | Every snapshot consumer (cargo economics, netback, hedge approvals, mandate usage, credit exposure: 3 repeats each) | One book per snapshot; `PriceBook.resolve` keeps the asked hub and period, so answers are unchanged (test compares) | M | Fixed |
| P2 | `/api/runtime/source-operations` ran 44 identical state queries | Reconcile called `session.get` per source on every read | `/api/sources` (schema inspection, already cached after first read) | One query; rows held in the identity map | M | Fixed |
| P3 | `/api/desk/today` 158 statements / 4.9 s; `/api/reports/catalogue` 97 / 5.8 s; `/api/discoveries` 2.3 s; `/api/fundamentals/forward-balance` 3.2 s | Composite reads of many sections; screen orders read 11 times on Today | — | Proposal: profile per section; Today's screen-order read once per request | M | Proposal |
| P4 | Missing indexes on hot reads | Storage and LNG reads filter `country IN (…) AND period_start_utc` (Today, NWE balance, reports) but the index is `(facility_id, period_start_utc)`; flow reads for the map filter `period_start_utc` and `kind` with no point, which `(point_id, period_start_utc)` cannot serve | `storage_observations`, `lng_observations`, `flow_observations` | Proposal: migration adding `(country, period_start_utc)` on storage and LNG and `(kind, period_start_utc)` on flows, after `EXPLAIN ANALYZE` on a production-sized store; deferred because seven branches carry migrations and the head literals are pinned in 13 places | M | Proposal |
| P5 | Glossary per-row requests | Checked: the glossary is one list read (12 ms); context is read on selection only | — | — | — | OK |

## Manual inputs: inventory (rule 19)

Wired (`meta.manual_inputs` on every response):

| Endpoint | Hand-entered fields stated |
|----------|----------------------------|
| `POST /api/research/route-cost`, `/netback`, `/feasibility`, `/allocation`, `/cash-valuation`, `/capacity-billing`, `/lng-economics-only` | every figure the caller set (sandbox calculations) |
| `POST /api/route-cost/calculate` | `flow_quantity`, the typed tariff legs' figures |
| `POST /api/lng/cargo-economics` | cargo figures typed per cargo (prices, slope, voyage costs), terminal inputs, `eua_eur_t` |
| `POST /api/lng/cargoes/{id}/plan/what-if` | `eta_utc`, `berth_delay_hours`, `laytime_hours`, `demurrage_per_day` |
| `POST /api/portfolio/lng-cargo-bid` (bid sheet) | cargo size, target margin, boil-off, charter |
| `POST /api/portfolio/sell-down-plan` | `da_price`, `wd_expected_price`, penalties, lot |
| `POST /api/optimization/storage-dispatch` | the facility and period figures |
| `GET /api/portfolio/position-ladder?shock=` (price shock scenario) | each tenor shock |

Not yet wired (each needs the route to collect what it read from a stored hand entry, so not
a one-line change): `GET /api/fundamentals/forward-balance` (temperature, Norway, LNG and
outage overrides; today `lines[].inputs = ["manual"]`), `POST /api/optimization/route`,
`/capacity`, `/contracts`, `/portfolio-network`, `/resource-pool`, `/nomination-window`,
`POST /api/route-cost/recommend`, `/lng-regas/assess`, `/resource-pool/optimize`,
`GET /api/capacity/cost` (a rate entered by hand in the FX check), `GET
/api/lng/cargoes/{id}/disruption-options` (pipeline days entered by hand, a hand FX rate),
`POST /api/research/spreads/evaluate` (the spec mixes choices and typed costs),
`GET /api/market/valuation-snapshots/{id}` (inputs of class `assumption`), the hedge planner
(`GET /api/portfolio/hedge-approvals`), gas-day bands entered by hand (`application/gas_day.py`).

Client wiring points for the UI reviewers (`<ManualInputsNote meta={response.meta} />` under
the result; each panel must first keep `response.meta`): `SellDownPanel.tsx` (sell-down),
`research/CargoStudy.tsx` (cargo economics), `CargoPlanView.tsx` (what-if),
`PositionLadderPanel.tsx` (shock scenario), the bid sheet panel, `app/model/
useOptimizationAssessment.ts` (storage dispatch), the route-cost calculator and the research
sandbox panels.

## Fixes in this branch

1. **One error envelope** (`api/error_handlers.error_body`, `api/errors.ApiError`): the router's
   own 404/405 enveloped; every refusal carries `error` (code), `params`, `fallback_message`;
   uncatalogued codes keep their name; code aliases. Gate `tests/contract/test_api_error_codes.py`.
2. **No-store rule** (`api/middleware/runtime_store_state.py`).
3. **Bounded reads** (`application/bounded_reads.py`) on seven calculation and list inputs.
4. **Ingestion**: `domain/dataops/retry.classify_script_failure`; EIA and IIP reports; demo
   catch-up partial reads; demo monitoring without an enrichment identity.
5. **Provenance**: `domain/ontology/provenance.is_simulated`; outage and observation rows carry
   `simulated`; the demo REMIT source is kept; `capacity_impact_mcm_d` is `None` when unknown.
6. **Performance**: one price book per valuation snapshot; one read of the source states.

Contract for the client reviewers adding i18n: translate `errors.<error>.message` with `params`;
show `fallback_message` when there is no entry. `detail` is unchanged for existing readers.
Success payloads: `meta.runtime_store` when the deployment has no store; `simulated` on market
observation and outage rows; `capacity_impact_mcm_d` may be `null`.

## Left for the owner

- Deploy decision: nothing here was deployed; the demo still runs `6621f46`.
- A2d (codes for success-payload notices), A4c (bounding `/api/market/observations`), O7
  (manual-input statement on every calculation) are API contract changes worth a short
  decision each.
- P4 indexes need a migration slot once the in-flight branches merge.
- The client type for `capacity_impact_mcm_d` (`number | null`) and the version handshake (L4)
  are client work.
- Disk: the shared host ran out of space during this audit (other sessions' stopped PostgreSQL
  containers hold about 7 GB of reclaimable Docker volumes).

## Structural plan

Owner standing permission (2026-11-26): contained improvements now; moves that would conflict
with the branches in flight (map, three UI reviews, half-built features, topology, hub identity)
are planned here and executed after they merge. Each step is a pure move with re-exports left
at the old import path for one release, its own commit, and the full unit/api/contract suites.

### Target backend structure

```
src/eurogas_nexus/
  api/            HTTP only: routes (thin), envelope, errors, middleware, dependencies
  application/    use cases grouped by bounded context (see below), no FastAPI imports
  domain/         pure models and rules; ontology/ holds the shared vocabulary
  db/             models and repositories; no HTTP types
  ingestion/      source adapters (transport, parse, normalise) - one package per provider
  core/           settings, outbound HTTP (one retry helper), clock
```

Bounded contexts for `application/` (134 flat modules today): `market/` (prices, price book,
quotes, FX, rates), `physical/` (flows, capacity, storage, LNG, outages), `portfolio/`
(positions, P&L, limits, credit), `lng/` (cargo, disruption, demurrage), `research/`,
`reports/` (exists), `dataops/` (ingestion runtime, freshness, source operations), `governance/`.

### Order of moves and risk

| Step | Move | Why | Risk |
|------|------|-----|------|
| 1 | One envelope builder for success responses (`api/envelope.py`: `envelope(data, *, source, notices, page)`), replacing the ten `_env` helpers | Root of A2d and A5: notices and paging in one place | Low (additive; each route keeps its output); touches every route module, so after the UI branches merge |
| 2 | Shared `Notice(code, text, params)`; `meta.notices` beside `meta.warnings` | A2d | Low, additive |
| 3 | `core/outbound_http.fetch_with_retry` and move the four hand-written retries onto it | I1 | Medium: each source's measured limits (IIP 20 s spacing) must be kept as parameters |
| 4 | Migrate the 39 remaining `_Sim` checks to `is_simulated`, lowering the ratchet | O1 | Low per site; a rule change for rows flagged only in metadata (intended) |
| 5 | Split oversized modules along their seams: `domain/research/weather_demand.py` (3,797 lines: fit, features, evaluation), `domain/lng/disruption.py` (3,007: options, simulation, ranking), `db/repositories/ecmwf_forecasts.py` (2,320: storage vs. derived series), `api/routes/public/research.py` (1,844), `application/desk_today.py` (1,757: one module per Today section) | Review and test cost | Medium: the LNG and research modules are being extended on other branches; do after they land |
| 6 | Group `application/` into the contexts above (moves with re-exports) | Navigation; ownership | High merge conflict risk now; last |
| 7 | Move HTTP refusals out of `db/repositories/strategy_access.py` (domain `AccessDenied`) | Layering (A6) | Low |
| 8 | Indexes (P4) in one migration | Hot reads | Low (expand-only) once measured |

### Client structure (plan only; not edited here)

| Item | Today | Target | Risk |
|------|-------|--------|------|
| `components/GasNetworkMap.tsx` | 2,870 lines: layers, interaction, detail, legend, data shaping | `map/` folder: `layers/*.ts` (one per layer, pure style builders), `useMapData.ts` (data shaping, testable), `MapInteractions.ts`, `GasNetworkMap.tsx` as composition | High while the map branch is open; do after it merges |
| `api/client.ts` (8,214 lines) and `stores/api.ts` (2,797) | One file of every DTO and call, a second store of every read | DTOs generated from the OpenAPI census into `api/types/`; calls grouped per context (`api/market.ts`, `api/physical.ts` …); the store split per workspace | Medium; generation removes hand drift between backend and client types (e.g. O2) |
| `styles/app.css` (8,380) and `styles/design-system.css` (4,564), `network-desk.css` (1,100), `controls.css` (894), `WorkspaceTopBar.css` (790) | Global sheets with overlapping rules | Design tokens in one file; component CSS modules co-located; delete rules no component uses (coverage from the Playwright run) | Medium: visual regressions; needs screenshot comparison |
| Duplicated models (`app/model/tickerItems.ts` 1,242 lines and the alert/cargo models, the client's own gas-day and hub code) | Client-side copies of backend rules | Client reads the backend's answer (gas day, hub identity from `hubid`, simulated flag) instead of re-deriving it | Medium; coordinate with the UI reviews |
| Error presentation | `errorPresentation.ts` reads `error`, `message_key`; not yet `params`/`fallback_message` | Read `params` and `fallback_message` (the UI reviewers' i18n work) | Low |
