# W4-01 — Unified Data Platform Surface

Status: **delivered (Wave 4)**. Authority:
[07_DATA_PLATFORM.md](07_DATA_PLATFORM.md) sections 2, 3 and 6,
[03_TARGET_PLATFORM_ARCHITECTURE.md](03_TARGET_PLATFORM_ARCHITECTURE.md) sections 3-4,
[11_CURRENT_TO_TARGET_GAP_MATRIX.md](11_CURRENT_TO_TARGET_GAP_MATRIX.md) rows
"Source Center", "Data entitlement", "Data architecture", "Reproducibility",
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 9-15 and 31-36,
and [W2-01](W2-01_EFFECTIVE_ACCESS_AND_EXPERIENCE_PROFILE.md) for the capability model.

## 1. What the wave required

Two of the four gap-matrix rows this wave owns were carried by earlier work:
"Source Center" was refactored by the data-operations slices (provider connectivity
is operator posture, served by `/api/sources` and `/api/runtime/source-operations`),
and "Data entitlement" already had a fail-closed per-principal implementation in
`security/identity.py`, `domain/dataops/entitlement.py` and
`api/dependencies/row_entitlement.py`. What was missing:

- a **business-facing Data Product contract** independent of provider
  implementation (gap row "Data architecture" → Unified Data Platform); and
- an **Analysis Snapshot** as a persisted reproducibility reference (gap row
  "Reproducibility", and the `analysis-snapshot` gap declared in
  [W1-01](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md) section 3, which is why
  `activeContextIsReproducible()` returns `false`).

## 2. Delivered

| Element | Where | What it does |
|---|---|---|
| Data Product catalogue as code | `src/eurogas_nexus/domain/data_platform/products.py` | Ten declared products (the eight named by 07 §2 plus two honest gap declarations), each with stable id, business name, domain, declared source families, simulated substitutes, entitlement families, time basis + gas-day calendar version, freshness expectation, explicit availability state, and the surfaces that serve it today |
| Catalogue read model | `src/eurogas_nexus/application/data_products.py` | Composes the declaration with the per-principal entitlement verdict and a measured freshness/provenance summary |
| Provenance reader | `src/eurogas_nexus/db/repositories/data_platform.py` | Per canonical table: row count, newest observation timestamp and per-label split. Exposes no credential, scheduler or retry state |
| Snapshot descriptor contract | `src/eurogas_nexus/domain/data_platform/snapshots.py` | The 07 §6 field list, the declared-availability model, the Active Context vocabulary, and the deterministic `content_hash` |
| Snapshot persistence | `src/eurogas_nexus/db/models/data_platform.py`, `alembic/versions/0034_analysis_snapshots.py` | `analysis_snapshots` table; expand-only, non-destructive migration |
| Snapshot service | `src/eurogas_nexus/application/data_platform_snapshots.py` | Builds a descriptor from the data that actually exists at creation time |
| API surface | `src/eurogas_nexus/api/routes/public/data_platform.py` | `GET /api/data-products`, `POST/GET /api/analysis-snapshots`, `GET /api/analysis-snapshots/{snapshot_id}` |
| Reproducibility reference on a produced result | `domain/route_cost/route_optimizer.py`, `api/routes/public/route_cost.py` | `POST /api/route-cost/recommend` accepts an optional `analysis_snapshot_id`, verifies it against persisted snapshots, and echoes it on the result |

## 3. The catalogue is anchored in code that exists

Every declaration is checkable, and `tests/contract/test_data_platform_contract.py`
checks it:

- a declared source family is a registered source, a simulated `*_Sim` producer
  that exists, or a public-baseline family;
- every `endpoint` surface is a path the app actually serves;
- every `module` and `command` surface is a real file;
- every `provenance_tables` entry is a mapped table.

Availability is stated, not implied:

| State | Meaning | Example today |
|---|---|---|
| `available` | A producer is implemented and a served surface returns canonical rows | European physical flow, capacity availability, storage/LNG (ENTSOG, GIE) |
| `operator_input_only` | Served, but values exist only after an operator import or seeding step | Portfolio position, route cost inputs |
| `simulated_only` | Served from canonical tables, but only `*_Sim` producers write rows today | NBP day-ahead market context, TTF/EU forward curve context |
| `declared_only` | The endpoint is honest but no source feeds it | Weather/demand context (`WEATHER_SOURCE_NOT_CONFIGURED`) |
| `not_implemented` | Required by the V2 target, no surface at all | LNG cargo flow context (Kpler connector shell only) |

## 4. User-facing data posture (07 §3)

The catalogue returns, per product, only what a business user may see: value time
basis, as-of, source/provenance summary, freshness, quality/confidence and
entitlement limitations. It returns no API key, secret value, scheduler internal or
retry trace — those stay in the operator posture (07 §4) already served by the
Source Center. `tests/api/test_data_platform_api.py` asserts the absence by key
name over the whole payload tree.

Freshness reuses `domain/monitoring/freshness.evaluate_freshness` and the data-ops
`FreshnessState` vocabulary (`FRESH`/`STALE`/`MISSING`/`NOT_EXPECTED`), so the
read side has exactly one definition of "live". Confidence
(`HIGH`/`MEDIUM`/`LOW`/`UNKNOWN`) is derived only from which declared families
actually have rows and whether freshness holds — never from a model score.

## 5. Entitlement is per principal and fail-closed

`evaluate_product_entitlement` reuses
`domain.dataops.entitlement.derived_result_access`, so a product is exposed only
when **every** contributing family is allowed — the same CR-09 derived-result
policy the rest of the platform already applies. There is no second
implementation of family matching and no new permission category.

A product whose required family the caller is not entitled to is reported as
`restricted`:

- the product entry is **still present** in the catalogue with its declaration;
- `entitlement.status` is `restricted`, with required/granted/restricted family
  **counts** — the names of families the caller lacks are never echoed, matching
  the no-echo rule in `api/dependencies/row_entitlement.py`;
- `provenance` is `null`. It is not an empty block and not a zero, because a zero
  would read as a measured fact about licensed data the caller may not see.

The legacy deployment-token service principal keeps its previous
single-trust-domain reach, exactly as the row-entitlement compatibility rule
requires; `tests/api/test_data_platform_api.py` pins that too.

## 6. Analysis Snapshot v1

The descriptor carries every 07 §6 field: `snapshot_id`, `as_of_utc`, `gas_day`,
time basis and calendar version, market data versions, network/capacity version,
portfolio version, contract/resource versions, tariff/FX, weather/demand
assumptions, manual assumptions, model/calculation versions and entitlement
context.

Version references are **measured**, not fabricated: each one is a real per-table
row count, newest observation timestamp and a `version_ref` hash over that summary.
A field with no implementation is stored as `unavailable` with a stable reason
code in `field_availability_json` — the schema accepts the value the day a
producer appears, without a shape change. Today that is
`weather_demand_assumptions` (`WEATHER_SOURCE_NOT_CONFIGURED`).

The same honesty applies to absence of evidence: with no runtime database every
version field is `unavailable` (`RUNTIME_DATABASE_NOT_CONFIGURED`) and the
snapshot carries the warning; with a database but no rows a field is
`unavailable` (`NO_RUNTIME_ROWS`).

`snapshot_id` is the reproducibility reference. `content_hash` is a stable
SHA-256 over the canonical payload, and a reader can recompute it from the
published response — `tests/api/test_data_platform_api.py` does exactly that.

The Active Context is persisted with the descriptor. The backend accepts the
dimensions it can express and **refuses** (`422 active_context_key_unsupported`)
the ones it cannot, naming `organization` and `decision_case` from the W1-01 gap
table instead of dropping them silently.

### Wired run path

`POST /api/route-cost/recommend` (the run path with the fewest moving parts)
accepts an optional `analysis_snapshot_id`; when supplied, the id is verified
against persisted snapshots (`422 analysis_snapshot_not_found` when unknown, `503`
when no runtime database can verify it) and echoed on
`RouteRecommendationResult.analysis_snapshot_id`, so a produced recommendation
cites the version set it was computed against. The field is optional and
additive: callers that supply no reference are unchanged.

Still to wire (recorded, not forced): the resource-pool optimisation run, the
strategy/backtest run manifest, generated reports and agent evidence.

### Follow-up: the citation reaches every run path the product runs

The follow-ups above were delivered incrementally - the resource-pool optimisation run and the
strategy backtest then, and the analysis and report paths in this stretch - so every run path a
client surface actually runs now accepts, verifies and echoes the reference:

| Run path | Verified before the work | Echoed | Durable where |
|---|---|---|---|
| `POST /api/route-cost/recommend` | yes | `data.analysis_snapshot_id` | response only |
| `POST /api/route-cost/resource-pool/optimize` | yes | on the result | the tracked run's `snapshot_id` |
| `POST /api/strategy-runs` (`run_type=BACKTEST`) | yes - no run row or job is created when refused | on the result | the strategy run and its job |
| `POST /api/analysis/query` | yes - before the input snapshot is loaded and before any provider call | on the result, absent when nothing was cited | the persisted analysis record's output snapshot |
| `POST /api/reports/portfolio` | yes | on the report, absent when nothing was cited | the tracked `REPORT` job's `snapshot_id` |

Two things this follow-up deliberately states rather than implies:

- **Verification comes first on the analysis path** because that path can call an external
  provider. An unverifiable citation is refused before the call, so a bad reference cannot be
  paid for with a request to a third party.
- **The stored report record has no column for a cited reference.** Its sections and source
  references are unchanged, and the citation lives on the tracked run; adding a column is a
  migration, not something to imply. The analysis record needs no such column because the
  citation travels inside the result it already persists.
- **The Web client now cites a reference.** The client half of this item was open - it could not
  even list the snapshots a deployment recorded. The review task reads
  `GET /api/analysis-snapshots` (task-scoped, identity-gated, bounded to 25) and offers the
  deployment's own references in its report panel; the chosen id travels in the report payload
  as `analysis_snapshot_id`, and the citation is rendered from the *response* rather than from
  the picker, so a run that cited nothing shows nothing. Citing nothing is the default and
  leaves the payload byte-identical, an empty list is explained by what the deployment said
  (`runtime-db-not-configured` reads as "this deployment cannot list snapshots", not "none were
  ever recorded"), and no id is ever composed on the client.

- **What remains open:** the client reads and cites snapshots but does not *record* one - there
  is no "freeze this context" action yet, so a user can only cite a snapshot some other caller
  recorded.

### The catalogue has a client consumer

`GET /api/data-products` had no client consumer either, so the catalogue's honesty rules - the
ones section 3 states as contract - had no surface to be true on. The research surface now
carries a **Data Products** view (not a new page: V2 rule 9, and the catalogue belongs beside the
dataset catalogue it describes):

- `api/client.ts` gains the typed `DataProductDTO`/`DataProductCatalogueDTO` and the read;
- `app/model/dataProductModel.ts` keeps the three provenance states **apart** instead of
  collapsing them into one empty-looking cell: `measured` (the backend measured it), `restricted`
  (this caller is not entitled, and the backend withheld the block on purpose) and `unmeasured`
  (entitled, but no runtime database was configured). A withheld or unmeasured row carries
  `rowCount: null`, so the surface cannot print a zero that reads like "this product is empty" -
  while a genuinely measured zero stays a zero, because that one is a measurement;
- a restricted product is **listed** with its declared facts (name, case, availability, time
  basis, sources) and says why it is restricted, with no count in the provenance cell;
- a state this build has no label for is rendered as its own code, and a failed read is reported
  as an alert rather than shown as an empty catalogue.

Still open in this family: nothing in the product *records* an Analysis Snapshot, and the
`researchCapabilities` read remains without a consumer.

## 7. Access path (07 §7)

The allowed path is preserved: `Application API → Data Product/semantic service →
repository`. Clients and AI still reach data only through `/api`; no client reads
a table, and no client calls a provider.

## 8. Compatibility

- **API:** additive. Three new paths are pinned in
  `tests/contract/test_api_surface_stability.py` and declared in
  `API_CONTRACT_EVOLUTION_POLICY.md` (+ CN). `POST /api/route-cost/recommend`
  gains one optional request field and one additive response field; no existing
  path, parameter, status code or field changed.
- **DB:** one expand-only migration (`0034_analysis_snapshots`) creating one new
  table and three indexes on it. No existing table, column, constraint or row is
  touched; the previous application version runs unchanged against the migrated
  schema. `analysis_snapshots` joins `db/registry.py` required tables.
- **Security:** no permission widened or narrowed. Two new registry entries:
  `/api/data-products` READ and the two snapshot GETs READ, with
  `POST /api/analysis-snapshots` GOVERNED (the existing ANALYST floor) via
  `METHOD_ROUTE_PERMISSIONS`. No new `Permission` member, no new role, no change
  to `COMMERCIAL_DATA_PREFIXES` — the catalogue and the snapshot descriptor are
  declarations and lineage metadata, so a caller can always see that a product
  exists and that its own entitlement is limited; every value stays behind its
  own already-declared path.
- **Numerics:** unchanged. No existing calculation was touched; the route-cost
  recommendation adds only a reference echo and a verification lookup.
- **Client:** unchanged. No client code was modified.

## 9. Verification

- `tests/contract/test_data_platform_contract.py` — catalogue anchoring,
  availability honesty, descriptor field list, migration/model registration, path
  permissions and the commercial-boundary placement.
- `tests/api/test_data_platform_api.py` — catalogue posture and provenance,
  no-operator-internals assertion, restricted-product reporting, snapshot round
  trip, declared-absence fields, `content_hash` recomputation, entitlement
  context, 404/422/503 behaviour, role floor, and the snapshot citation on the
  route-cost recommendation.
- `tests/unit/test_data_platform_domain.py` — fail-closed entitlement evaluation,
  legacy-principal compatibility, descriptor hash stability and payload shape.
- `tests/unit/test_analysis_snapshot_migration.py` — the real `upgrade()` /
  `downgrade()` DDL executed on SQLite, asserting no pre-existing table is
  touched and the column set matches the model.
