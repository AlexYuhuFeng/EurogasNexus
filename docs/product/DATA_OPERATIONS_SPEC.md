# Data Operations Specification — CR-09

Status: normative for the CR-09 vertical slice. Repository behavior is the
authority; this document records the audited current state and the design
accepted by DSH Pro for production data operations.

## 1. Scope

Eurogas Nexus must be able to answer, from PostgreSQL-backed evidence:

- which sources are expected to run, when each should update, when each last
  attempted and last succeeded;
- whether current data is FRESH / LATE / STALE / MISSING / NOT_EXPECTED /
  UNKNOWN / RESTRICTED and why;
- how far behind the source is, which period is missing, and whether fallback
  was used;
- whether the provider is implemented, configured, connection-verified, data-
  validated, or certified for this deployment;
- whether this principal may see this row or this derived result;
- which upstream observation produced a normalized value and which run
  ingested it;
- what failed, whether retry is appropriate, whether recovery succeeded;
- whether downstream live results are now stale because upstream evidence
  changed or failed.

This remains decision support. Nothing in this milestone adds order,
nomination, or execution semantics.

## 2. Current-state audit (2026-09-07)

### 2.1 Registered providers

`src/eurogas_nexus/domain/ingestion/source_registry.py` is the single static
registry: **24 source systems**, with category, datasets, entitlement scope,
freshness expectation, credential requirements and certification stage.
Categories: 11 price, 8 tariff, 2 infrastructure, 1 FX, 1 weather, 1 LLM.
10 are licensed (credential-required); 14 are public. The registry is pure
data, import-safe, and is already backend-owned: the web client consumes the
result of `/api/sources` and holds no provider list of its own.

### 2.2 Implemented providers

- **Real normalizers** (no live execution inside the package): ECB
  (`public_sources.py` XML), ENTSOG connection points / operator point
  directions / flows / capacity (`public_sources.py` JSON), GIE AGSI storage
  and ALSI LNG (`public_sources.py` JSON).
- **Explicit live fetch script**: `scripts/ops/ingest_public_sources.py`
  (operator-invoked, fail-closed entitlement/certification gates, bounded
  HTTP, raw archive, idempotent upsert, persisted `ingestion_runs`).
- **Connector shells** under `src/eurogas_nexus/ingestion/connectors/` for
  ECB, ENTSOG, GIE, EEX, ICE OCM, Trayport, Weather. These are mock shells;
  they never call a provider at import time and return empty payloads.
- **Cost-source connector framework** for TSO tariffs and LNG slots;
  `JsonCostObservationConnector` is the only machine-readable connector and
  returns `()` for unconfigured or failed responses.

### 2.3 Simulated/reference providers

`src/eurogas_nexus/ingestion/simulated_market_prices.py` and
`scripts/ops/ingest_simulated_market_prices.py` inject `EEX_Sim`,
`ICE_OCM_Sim`, `Trayport_Sim`, `ICIS_Sim` rows. Simulated sources are never
treated as native live data and are explicitly labelled `simulated`.

### 2.4 Credentialed providers

`provider_credentials` stores backend-owned encrypted payloads, redacted
previews and fingerprints. Plaintext is returned once on submission and never
again. Public routes cover list/set/rotate/status/local-validation/
connection-test. **Only DEEPSEEK/LLM has a governed live connection test.**
ECB/ENTSOG are public. GIE supports an env key or encrypted store in the
public-ingestion script. EEX, ICE OCM, Trayport, Kpler, Platts, ICIS, Argus,
Weather remain credential-configured-at-most; none has a governed live test.

### 2.5 Ingestion invocation model

Operator-invoked scripts only:

- `scripts/ops/ingest_public_sources.py --source ...`
- `scripts/ops/run_public_ingestion_worker.py` (supervisory loop, >=60 s
  interval)
- `scripts/ops/ingest_simulated_market_prices.py` (development/trial-gated)
- `scripts/ops/refresh_cost_observations.py`

There is no persisted production scheduler. `ingestion_runs` is the only
history and it stores `run_id/source_name/status/started/finished/notes`;
row counts are parsed from free text. No run issues, retry count, trigger
type, or error category columns exist.

### 2.6 Scheduling model

CR-06 shadow scheduling is the reusable production pattern: typed schedules,
PostgreSQL truth, unique `(monitor, scheduled_for)`, SKIP LOCKED claiming,
scheduler heartbeat. Public ingestion still depends on an external worker
loop (`run_public_ingestion_worker.py`); browser timers are not used for
ingestion.

### 2.7 Retry behavior

`application/source_operations.py` owns bounded exponential retry with source
policies (ENTSOG 3/30s, GIE 3/60s, ECB 3/300s, tariffs 2/60s, Weather 3/60s).
`ingest_public_sources.py` has HTTP transport retry honoring `Retry-After`.
Retries are **not failure-category aware**: every exception retries the same
way, including authentication, entitlement and schema failures.

### 2.8 Quality checks

Quality exists as row-level `quality_score` and metadata labels, plus
`data_quality/contracts.py` shells. There is no reusable check framework, no
structured issue persistence, and no run-level quality summary.

### 2.9 Freshness logic

`domain/monitoring/freshness.py` computes three states (`live/stale/unknown`)
from newest `observed_at_utc`. Source Center overrides with DB counts. It has
one threshold per source, no LATE/MISSING/NOT_EXPECTED/RESTRICTED states, no
calendar awareness, no latency decomposition, and no last-attempt-vs-last-
success distinction.

### 2.10 Source certification

`provider_certifications` + `domain/ingestion/certification.py` implement a
simulated-to-live gate (`unverified` → `simulation_matched` →
`live_validated`). `live_validated` requires `simulated_shape_match` and
`live_sample_validation`. This is correct and fail-closed, but the model is
provider-level only; it does not persist dataset, environment, adapter
version, credential label, entitlement scope, sample period, tests performed,
expiry, or evidence reference.

### 2.11 Entitlement enforcement

`governance/entitlement.py` and `security/identity.py` provide fail-closed
family/scope logic. `/api/market/observations` and `/api/market/quotes` filter
rows by the authenticated principal. Other read surfaces (physical, storage,
LNG, weather, cost observations, route candidates, reports, strategy/shadow
evidence) do not apply principal data-scope filtering; several return
unfiltered rows. Derived results do not consistently propagate source scope.

### 2.12 Lineage

Every observation row carries `source_system`, `source_reference`,
`source_record_id`, `observed_at_utc`, `freshness`, `research_only`. Raw
payloads are archived with SHA-256 when under the size limit and when
permitted. Gaps: normalized rows do not reference `ingestion_runs.run_id`;
archive rows do not reference a run; parser/adapter versions are not
persisted; strategy/backtest/shadow/review evidence rows have source refs but
no data-operations lineage record.

### 2.13 Metrics/logging

There is no metrics exporter. Logging is mostly `print()` from scripts.
`X-Request-Id` middleware exists and audit rows accept a request id. No
structured data-operations logger, no redaction helper for payload bodies.

### 2.14 Known production gaps (pre-CR-09)

1. No persisted scheduler, no restart-safe duplicate prevention for
   ingestion, no scheduler heartbeat.
2. `ingestion_runs` has no structured run contract.
3. Retry/circuit behavior is not failure-category aware.
4. Freshness is three-state, single-threshold, no market calendar, no
   latency decomposition.
5. Certification model is provider-only and has no deployment/dataset
   evidence fields.
6. Row-level entitlement is limited to two market routes; derived results
   can bypass it.
7. No data-operations metrics or structured logs.
8. Source Center is catalog/posture focused, not an operator pipeline view.

## 3. Source registry design

The existing `domain/ingestion/source_registry.py` remains the **canonical
compiled baseline**. CR-09 adds a typed layer
(`src/eurogas_nexus/domain/dataops/registry.py`) that derives `
SourceDefinition` records from the same 24 registry rows and supplies
operational semantics:

```text
SourceDefinition
  source_id, provider, dataset, source_class, access_mode,
  entitlement_scope, credential_fields, certification_required,
  schedule (typed spec), timezone, freshness_policy
  (normal/late/stale thresholds), retry_policy, rate_limit_policy,
  calendar, adapter_version, raw_retention_policy
```

`source_class` is one of `PUBLIC | LICENSED | BROKER | EXCHANGE | OPERATOR |
MODEL | REFERENCE | SIMULATED`. `access_mode` is `PUBLIC_HTTP | KEYED_HTTP |
SOCKET_FEED | FILE_UPLOAD | NONE`. Unknown combinations fail closed
(`UNKNOWN`).

The 24-source mapping is explicit and tested: simulated sources are
`SIMULATED`; EEX/ICE_OCM are `EXCHANGE`; Trayport and broker sources are
`BROKER`; Kpler/Platts/ICIS/Argus are `LICENSED`; ENTSOG/GIE/ECB/TSO tariffs
are `PUBLIC` (GIE is keyed HTTP in practice but classified `PUBLIC` with
credential_fields for the key); operator-owned rows are `OPERATOR`;
`DEEPSEEK` is `MODEL`.

## 4. Scheduling

Schedule spec is persisted in PostgreSQL `source_runtime_states` and
reconciled from the compiled registry every scan. Types:

- `INTERVAL` — deterministic seconds anchored at source activation.
- `DAILY` — daily `HH:MM` in the source timezone.
- `MARKET_RELATIVE` — publication offset relative to the corrected CAM
  gas-day calendar (`EU-CAM-UTC-2025`) for gas-market windows.
- `EXTERNAL` — expected via operator/integration trigger; scheduler only
  raises LATENESS after the configured expected window.

`next_scheduled_instant()` is pure and deterministic. The scheduler:

1. reconciles enabled source state rows (`enabled` is backend-owned);
2. scans due rows with `next_run_at_utc <= now`;
3. claims rows with `SELECT ... FOR UPDATE SKIP LOCKED` (PostgreSQL),
   bounded to a run limit;
4. inserts one QUEUED `ingestion_runs` row per due source and advances the
   source's `next_run_at_utc` **before** execution;
5. worker claims QUEUED runs by `scheduled_for_utc`, marks RUNNING, executes
   the adapter, then writes SUCCEEDED / SUCCEEDED_WITH_WARNINGS / FAILED /
   CANCELLED.

Restart safety: a QUEUED/RUNNING run older than the stale threshold is
recovered as FAILED with `INTERNAL:STALE_RUN` and its source is scheduled
again according to the missed-run policy. A partial unique index
`(source_id, scheduled_for_utc) WHERE trigger_type='SCHEDULED'` makes
duplicate scheduled ingestion impossible at the database layer.

Missed-run policy is bounded: `CATCH_UP_LIMITED` executes at most one catch-up
run per scan; `SKIP` marks the gap; `RUN_LATEST_ONLY` coalesces.

## 5. Market calendars

A source can declare `calendar: ALWAYS_OPEN | GAS_MARKET | WEEKDAYS_ONLY`.
When a `GAS_MARKET` source is inside its expected publication window the
scheduler expects updates; outside a declared closed window the freshness
engine returns `NOT_EXPECTED` rather than CRITICAL. `NOT_EXPECTED` is computed
only from backend calendar + schedule, never from "no rows arrived".

## 6. Freshness SLAs

Each `SourceDefinition` carries three backend-owned thresholds:

```text
freshness_policy = {
  "normal_max_age_minutes": N,   # <= N  -> FRESH
  "late_after_minutes": L,       # >  N  -> LATE
  "stale_after_minutes": S,      # >  L  -> STALE
}
```

Evaluation (`domain/dataops/freshness.py`) uses, in priority order per source
basis:

1. `publication/observed_at_utc` where the provider publishes one;
2. otherwise `available_at_utc` where known;
3. otherwise `ingested_at_utc`.

States: `FRESH`, `LATE`, `STALE`, `MISSING` (scheduler expected and has
never succeeded), `NOT_EXPECTED` (calendar/schedule says closed), `UNKNOWN`
(no schedule or no timestamp evidence), `RESTRICTED` (entitlement/certification
blocks evaluation). Deterministic: same inputs and clock always produce the
same state.

Examples carried in the registry: ENTSOG normal 60m/late 120m/stale 360m;
GIE 360m/720m/1440m; ECB 1440m/late 2880m/stale 4320m; licensed realtime
feeds 1m/5m/30m but only when a live adapter is actually connected;
30-day tariff references 43200m/64800m/129600m. There is no global
"older than 24h" rule.

## 7. Latency definitions

- **source_age_seconds** = `now - observed_at_utc` (provider publication or
  observation time).
- **ingestion_lag_seconds** = `first_persisted_at_utc - available_at_utc`
  (when availability is known; otherwise NULL, never fabricated).
- **pipeline_lag_seconds** = `run.completed_at_utc - run.started_at_utc`
  (measured per successful run).

The runtime state row stores all three. `source_age` drives freshness;
`ingestion_lag` drives provider/pipeline latency diagnosis; `pipeline_lag`
drives scheduler performance budgets.

## 8. Ingestion runs

`ingestion_runs` is extended, preserving every existing row:

```text
source_id, dataset, trigger_type (SCHEDULED|MANUAL|BACKFILL|RECOVERY|
  CERTIFICATION_TEST), requested_at_utc, scheduled_for_utc, started_at_utc,
  completed_at_utc, status (QUEUED|RUNNING|SUCCEEDED|
  SUCCEEDED_WITH_WARNINGS|FAILED|CANCELLED), window_start_utc,
  window_end_utc, attempt_number, rows_received, rows_accepted,
  rows_rejected, rows_inserted, rows_updated, duplicate_count,
  quality_warning_count, error_category, error_code, correlation_id,
  adapter_version, retry_of_run_id, fallback_used, lineage_refs
```

`notes` remains for human-facing detail. Logs are not the run history;
`ingestion_run_issues` stores structured issues with `quality_code`,
`severity`, `field`, `observation_reference`, `message`, `rule_version`.

## 9. Retry policy

`domain/dataops/retry.py` classifies failures before any retry:

`NETWORK_TRANSIENT`, `RATE_LIMITED`, `AUTHENTICATION`, `ENTITLEMENT`,
`PROVIDER_UNAVAILABLE`, `BAD_RESPONSE`, `SCHEMA_CHANGED`,
`QUALITY_REJECTED`, `CONFIGURATION`, `INTERNAL`.

Retry only: `NETWORK_TRANSIENT`, `RATE_LIMITED`, `PROVIDER_UNAVAILABLE`
(HTTP 500/502/503/504), `BAD_RESPONSE` (bounded), and `INTERNAL` (bounded).
Never retry: `AUTHENTICATION`, `ENTITLEMENT`, `SCHEMA_CHANGED`,
`QUALITY_REJECTED`, `CONFIGURATION`.

Backoff is exponential with full jitter
(`delay = base * 2**attempt`, jittered to `[delay/2, delay]`), bounded by
`max_delay_seconds` and `retry_max`. `RATE_LIMITED` honors `Retry-After`
first. Rate-limit policy declares `max_requests_per_interval`,
`interval_seconds`, `min_spacing_seconds`, `max_concurrency`; unknown vendor
limits remain explicit configuration gaps, never invented.

## 10. Circuit breaker

Per source in `source_runtime_states`:

- `HEALTHY` after a success;
- `DEGRADED` at 3 consecutive classified failures;
- `OPEN_CIRCUIT` at the configured threshold (default 6) — automatic retries
  suppressed until `recovery_probe_at_utc` (default 15 minutes later);
- operator may `DISABLED` a source explicitly.

Recovery probes are `RECOVERY` trigger runs. Success resets consecutive
failures and restores `HEALTHY`. Circuit state is persisted, not in-memory.

## 11. Backfill

Operator-triggered backfill requests persist a `trigger_type=BACKFILL` run
with `window_start_utc`, `window_end_utc`, `reason`, and optional `dry_run`.
Backfill never claims a SCHEDULED slot and never masquerades as live
ingestion. Backfilled rows retain the provider's original
`observed_at_utc/period_*` timestamps; only pipeline activity time changes.
Backfill parameters are bounded (one source, max window, reason required).

## 12. Idempotency

`upsert_observation_rows` already upserts by natural primary key and preserves
first-seen `observed_at_utc`. CR-09 keeps that contract and adds:
duplicate count is recorded on every run, uniqueness indexes are added where a
natural key is stable, and providers without stable IDs must define a
deterministic canonical identity in their adapter before live ingestion is
allowed. Dedupe is never solely `price + timestamp` when source semantics need
more fields.

## 13. Raw vs normalized and schema drift

The boundary remains: provider payload -> parser -> canonical validation ->
normalized observation -> downstream usage. Raw licensed payloads are never
served by public APIs; when retention is prohibited, only hash/lineage
metadata is stored. `SCHEMA_CHANGED` is a first-class failure category:
unexpected missing required fields, type changes, empty-but-expected
responses and unknown product codes fail visibly, never silently.

## 14. Quality framework

`domain/dataops/quality.py` defines reusable check codes:

`REQUIRED_FIELD`, `TYPE`, `UNIT`, `CURRENCY`, `TIMESTAMP`, `DUPLICATE`,
`RANGE`, `NEGATIVE_VALUE`, `SEQUENCE_GAP`, `DELIVERY_WINDOW`,
`HUB_MAPPING`, `PRODUCT_MAPPING`, `OUTLIER`, `CROSS_SOURCE_CONSISTENCY`.

`OUTLIER` is `WARNING`/`REVIEW`, never automatic deletion. Run quality
summaries are `PASSED`, `PASSED_WITH_WARNINGS`, `FAILED`. Every issue has a
stable code, severity, field, observation reference, message and rule
version.

## 15. Lineage

Minimum normalized-row lineage:

```text
normalized row -> source_system -> provider/source reference
-> ingestion run id -> observed_at_utc -> adapter_version
-> content hash (where permitted)
```

CR-09 adds `lineage_refs` and `adapter_version` to runs; the ingestion script
records `run_id` into each normalized row's `metadata_json.ingestion_run_id`
(and later migrations can promote that to a column). Downstream route
snapshots, strategy evidence, scenario/optimizer runs and review results
retain source refs; derived results are filtered by the same source scope
(section 18), they do not copy opaque raw values.

## 16. Certification

Implementation != configuration != certification.

States per provider/dataset/environment:

`NOT_IMPLEMENTED`, `IMPLEMENTED`, `CONFIGURED`, `CONNECTION_VERIFIED`,
`DATA_VALIDATED`, `CERTIFIED`, `CERTIFICATION_EXPIRED`, `BLOCKED`.

The existing simulated-to-live gate remains authoritative for live market
use; its three legacy stages map to the new state ladder. Certification
records persist provider, dataset, environment, `tested_at_utc`,
`tested_by`, `adapter_version`, credential label (never the secret),
entitlement scope, sample period, `tests_performed`, result, `expires_at_utc`,
evidence reference, and notes. Adapter-version changes move a `CERTIFIED`
state back to `DATA_VALIDATED` (recertification required) by policy; expiry
moves it to `CERTIFICATION_EXPIRED`. Mocked tests can only record
`IMPLEMENTED`/`CONFIGURED`; they can never produce `CERTIFIED`.

## 17. Licensed-data boundary

Per licensed source, the registry carries `raw_retention_policy`,
`api_exposure`, `logging_allowed`, `export_allowed`, `llm_allowed`. Defaults
are fail-closed: no raw payload API exposure, no provider payload logging,
no export, no LLM use unless an explicit policy row says otherwise. Public
ingestion archives raw payloads only for sources whose policy permits it and
under the existing size bound; ENTSOG/GIE archives remain bounded. No
plaintext credential is ever stored.

## 18. Entitlement propagation

A row or derived result is accessible only when the principal's data scope
allows every restricted source family it depends on. Public baseline families
(`operator-input`, `ENTSOG`, `GIE`, `ECB`, `Weather`) remain visible to every
active principal; commercial families (`EEX`, `ICE_OCM`, `Trayport`, `ICIS`,
`Argus`, `Kpler`, `Platts`) require an explicit `*` or family grant.

- Direct rows: filtered per row by `source_system`.
- Derived results: if any contributing restricted family is not in the
  principal's scope, the result is hidden or rejected (403 with no source-
  specific detail for scope gaps); safe aggregated exposure is allowed only
  where a documented transformation policy exists, and CR-09 defines none,
  so default is **fail closed**.
- Counts, aggregates, error messages, metadata and exports are computed
  **after** filtering; no unauthorized row may leak through a count or an
  error detail.
- Frontend hiding is UX only; backend routes are authoritative.

Representative principal test matrix: `PUBLIC_ONLY`, `EEX_ALLOWED`,
`ICIS_ALLOWED`, `MULTI_SOURCE`, `OPERATOR`.

## 19. Observability

No new external dependency. CR-09 adds:

- `GET /api/runtime/metrics` (Prometheus text exposition) with
  `eurogas_ingestion_runs_total`, `eurogas_ingestion_failures_total`,
  `eurogas_ingestion_duration_seconds`, `eurogas_source_freshness_seconds`,
  `eurogas_source_lag_seconds`, `eurogas_source_rows_received_total`,
  `eurogas_source_rows_rejected_total`,
  `eurogas_source_consecutive_failures`,
  `eurogas_source_scheduler_overdue`,
  `eurogas_entitlement_denials_total`,
  `eurogas_source_certification_state`. Labels are low-cardinality:
  `source_id`, `dataset`, `error_category`, `state` only. Never raw URLs,
  user emails, or observation ids.
- Structured JSON data-operations events
  (`application/dataops_observability.emit_event`) with `timestamp`, `level`,
  `service`, `event`, `source_id`, `run_id`, `correlation_id`,
  `error_category`, `adapter_version`. A redaction filter removes credential
  values and provider payload bodies before emission.
- Correlation: scheduler -> claim -> run id -> adapter version -> error
  category. API request ids are already attached by middleware.
- Tracing remains lightweight: spans are emitted at scheduler claim, provider
  call boundary, parser/validation, and persistence for diagnostic value only;
  not every loop.

## 20. Downstream fail-closed behavior

- **Market**: Source Center and market cockpit show backend-owned freshness
  state; stale rows are labelled, never presented as current.
- **Strategy**: CR-04/CR-06 already fail on missing evidence and the shadow
  runtime blocks stale required data (`DATA_STALE` blockers). No change to
  historical run rows.
- **Scenario/Optimizer**: source provenance is checked before live
  recomputation; unknown/restricted/stale required sources block or warn
  according to the strategy provenance policy.
- **Review**: evidence degradation is displayed from persisted run warnings.
- **Invalidation**: a source becoming stale never mutates an historical
  persisted run. Historical runs remain valid evidence at their recorded
  cutoff. Only current/live candidate views change.

## 21. Performance

Measure before optimizing. CR-09 adds
`scripts/ops/dataops_benchmark.py` which measures, against the configured
PostgreSQL store: scheduler scan latency, run claim latency, freshness
calculation for 24 sources, issue-list read, and entitlement filter overhead.
Bulk writes stay in the existing repository path (`executemany`-style
`pg_insert`). No one-transaction-per-row loops are introduced.

## 22. Operator workflows

Source Center hierarchy: **Overview / Pipelines / Certification /
Credentials**. Overview is a compact sortable table with Source, Dataset,
State, Freshness, Last success, Last attempt, Next run, Lag, Rows,
Certification, Entitlement, Failures, Action. Pipelines shows one selected
source's schedule, runs, row counters, quality warnings, retry/circuit state,
adapter version, recent errors and lineage sample, with `Run now`,
`Backfill`, `Retry failed`, `Enable/Disable` actions behind precise
confirmation. Certification shows provider/dataset/environment/state/last
certified/adapter/entitlement/evidence/next action. Credentials show
Configured/Missing/Invalid/Entitlement missing/Connection verified and never
return plaintext.

Runtime workspace gains a source-operations health strip: scheduler
heartbeat, sources scheduled/healthy/stale/failed, certification gaps,
entitlement failures, backlog depth, oldest overdue source.

Operator API additions (all under `/api`, OPERATOR permission):

- `GET  /api/sources/{source_id}/health`
- `GET  /api/sources/{source_id}/runs`
- `POST /api/sources/{source_id}/run`
- `POST /api/sources/{source_id}/backfill`
- `POST /api/sources/{source_id}/retry`
- `PATCH /api/sources/{source_id}/enabled`
- `GET  /api/source-certifications`
- `POST /api/source-certifications/{source_id}/certify`

Existing `/api/sources` and `/api/ingestion-runs` remain compatible.

## 23. Known limitations after CR-09

- Commercial live adapters for EEX, ICE OCM, Trayport, Kpler, Platts, ICIS,
  Argus, broker feeds and Weather remain not connected in this repository;
  they cannot be certified here and remain `NOT CERTIFIED - credential/
  entitlement unavailable`.
- GIE remains the only licensed live key path; its connector is still mock
  in-package with live fetch in the operator script.
- `source_runtime_states` is one row per source; dataset-level runtime state
  is represented in `ingestion_runs.dataset` and certification rows.
- No distributed job queue is introduced; SKIP LOCKED claims over PostgreSQL
  provide multi-process safety for the scheduler/worker pair in this
  deployment shape.
- Full company identity lifecycle, SCIM, corporate SSO, billing, contract
  management and arbitrary redistribution remain out of scope (CR-10).
- Prometheus text exposition is pull-based; push/scrape wiring belongs to
  deployment, not application code.
