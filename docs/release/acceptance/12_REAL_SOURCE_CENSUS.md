# 12 — Real source census and GIE AGSI/ALSI transport integration

Task: **REAL-SOURCES-01**. Date: 2026-10-10. Author: DeepSeek routine worker; reviewer: Astra.

This census is an evidence record, not a certification. It separates four statuses that must never be
collapsed:

* **implemented** — repository code performs a real transport read for the source;
* **protocol-tested** — documented, development-only fixtures drive the transport/normalizer tests;
* **live-tested (read-only)** — a bounded read-only probe reached the provider and validated the
  response envelope; no source row was persisted;
* **customer-ready** — implemented + protocol-tested + live-tested + rights/attribution + entitlement
  + certification + customer-artifact exclusion all satisfied.

**Nothing in this repository is customer-ready today.** Only three sources have a real fetch path
(ECB, ENTSOG, GIE). Seven named connector classes exist, and exactly one of them (GIE) no longer
inherits `MockConnector`. Three commercial connector shells and a set of registry-only sources have no
transport at all.

Machine-readable companion (safe, secret-free): `.dnx-out/real-sources-20261010/source-inventory.json`.

## 1. Reconciliation: 24 registered UI sources

The registry is the static source of truth (`src/eurogas_nexus/domain/ingestion/source_registry.py`,
`registered_sources()` at `:78`; the docstring at `:8` states 24). Count confirmed: **24**. Typed
operational overrides live in `src/eurogas_nexus/domain/dataops/registry.py:63-154`.

| # | source_id | system | category | real transport in repo | code path | status | exact blocker |
|---|---|---|---|---|---|---|---|
| 1 | src-ecb | ECB | fx | public HTTPS XML | `scripts/ops/ingest_public_sources.py:215` | implemented + protocol-tested | not live-tested in this slice |
| 2 | src-entsog | ENTSOG | infrastructure | public HTTPS JSON API | `scripts/ops/ingest_public_sources.py:261,347,381` | implemented + protocol-tested | single-limit fetch; capacity path has no raw archive; certification gate |
| 3 | src-gie | GIE | infrastructure | keyed HTTPS JSON API (`x-key`) | `scripts/ops/ingest_public_sources.py:412`; `src/eurogas_nexus/ingestion/gie_transport.py` | implemented + protocol-tested + live-tested (read-only) | certification record absent; no compatible fallback; attribution review |
| 4 | src-national-gas-nts | NationalGasNTS | tariff | none | registry only; counts from `tso_tariffs` | not implemented | no adapter; REST contracts not retrieved; only dev seed writes tariffs |
| 5 | src-bbl | BBL | tariff | none | registry only | not implemented | no adapter |
| 6 | src-iuk | IUK | tariff | none | registry only | not implemented | no adapter |
| 7 | src-gts | GTS | tariff | none | registry only | not implemented | no adapter |
| 8 | src-natran | NaTran | tariff | none | registry only | not implemented | no adapter |
| 9 | src-german-tso | GermanTSO | tariff | none | registry only | not implemented | no adapter |
| 10 | src-fluxys-belgium | FluxysBelgium | tariff | none | registry only | not implemented | no adapter; EDP manual not reviewed |
| 11 | src-cnmc-enagas | CNMCEnagas | tariff | none | registry only | not implemented | no adapter |
| 12 | src-eex | EEX | price | none (operator file parser only) | `src/eurogas_nexus/ingestion/eex_ngp.py:234,307` | parser only; **connector shell is a mock** | no Hub/DataSource transport; specs/rights unverified; 15-min intraday delay |
| 13 | src-eex-sim | EEX_Sim | price | synthetic generator | `src/eurogas_nexus/ingestion/simulated_market_prices.py` | simulated (dev/test only) | not customer-deliverable by design |
| 14 | src-ice-ocm | ICE_OCM | price | none | `src/eurogas_nexus/ingestion/connectors/ice_ocm.py:17` | **mock shell** | no ICE Data Services product/spec selected |
| 15 | src-ice-ocm-sim | ICE_OCM_Sim | price | synthetic generator | `simulated_market_prices.py` | simulated (dev/test only) | not customer-deliverable by design |
| 16 | src-trayport | Trayport | price | none | `connectors/trayport.py:17` | **mock shell** | Trayport protocol/SDK unretrieved |
| 17 | src-trayport-sim | Trayport_Sim | price | synthetic generator | `simulated_market_prices.py` | simulated (dev/test only) | not customer-deliverable by design |
| 18 | src-platts | Platts | price | none | registry + credential entry only | not implemented | no adapter; no contract |
| 19 | src-icis | ICIS | price | none | registry + credential entry only | not implemented | no adapter (simulated `ICIS_Sim` only) |
| 20 | src-icis-sim | ICIS_Sim | price | synthetic generator | `simulated_market_prices.py` | simulated (dev/test only) | not customer-deliverable by design |
| 21 | src-argus | Argus | price | none | registry + credential entry only | not implemented | no adapter; no contract |
| 22 | src-kpler | Kpler | price | none | registry only | not implemented | no adapter; declared not implemented in `domain/data_platform/products.py:689` |
| 23 | src-weather | Weather | weather | none | `connectors/weather.py:17` | **mock shell** | no weather provider selected |
| 24 | src-deepseek | DEEPSEEK | ai | HTTPS LLM API (credential test) | `api/routes/public/credentials.py:255-284` | implemented (LLM, not market data) | not a market-data feed |

Totals reconcile to 24: 3 real market/infrastructure fetch paths (ECB, ENTSOG, GIE); 1 operator-file
parser with no network (EEX NGP); 3 sources whose only code is a `MockConnector` shell (ICE_OCM,
Trayport, Weather); 12 sources with only a registry/credential/tariff row and no adapter (Platts, ICIS,
Argus, Kpler and the eight tariff TSOs); 4 simulated generators; 1 real LLM call (DEEPSEEK). GIE was
converted from a mock shell; 6 connector classes still inherit `MockConnector` (ECB, EEX, ENTSOG,
ICE_OCM, Trayport, Weather), but ECB and ENTSOG are served by the real ingestor regardless.

### 1.1 Connector classes vs live routes (do not conflate)

All connector modules under `src/eurogas_nexus/ingestion/connectors/` except `gie.py` inherit
`MockConnector` (`base.py:45-79`), whose `fetch()` returns an empty `IngestionPayload` and performs no
network I/O. They have **no runtime call site**; only `tests/contract/test_connector_contracts.py`
imports them. The real live routes are in `scripts/ops/ingest_public_sources.py`, which does **not**
import the connector shells. A connector class existing is therefore not evidence of a live source.

## 2. Per-product transport detail

### 2.1 ECB (public FX reference rates)

* Transport: `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` via `httpx` with bounded
  retry (`:83`, `:215-259`, `_get_with_retry` at `:685`). On Windows a PowerShell fallback exists
  (`:564`) that bypasses the client policy — a defect, not a product fallback.
* Default: enabled (`domain/dataops/registry.py:64-79`: DAILY 16:10 Europe/Berlin, weekdays only).
* High-frequency option: none (daily reference rates).
* Compatible fallback: none needed; source is public.
* Cadence vs delay: one daily pull; no delay claim in code.
* Rights/auth: public; no key; not export-restricted (`CERTIFICATION_REQUIRED_SOURCES` at `:79`).
* Status: implemented + protocol-tested; live-tested in this slice: no.

### 2.2 ENTSOG (flows, capacity, reference network)

* Transport: public HTTPS JSON API `https://transparency.entsog.eu/api/v1/...` (`:84-88,261,347,381`).
* Flows: one request, `limit=args.limit`, `indicator="Physical Flow"` (`:351`), upserts
  `flow_observations`, raises when empty (`:347-379`).
* Capacity: four sequential requests (Firm Technical / Firm Booked / Interruptible Booked / Nomination,
  `:93-98`) and **no raw archive** (`:381-410`).
* Reference: connection points + operator point directions, `limit=max(limit,1000)` (`:261-345`),
  scoped replace of reference tables.
* Default: enabled (`registry.py:80-94`: INTERVAL 3600 s, gas-market calendar).
* High-frequency option: none; hourly polling is the configured cadence.
* Compatible fallback: none declared.
* Rights/auth: public platform; export-restricted; certification required (`:79`).
* Status: implemented + protocol-tested; the **single-limit fetch is a known truncation risk** (the
  provider's `limit`/pagination semantics were not implemented here), and the capacity path lacks an
  equivalent raw archive. Exact blocker: certification record + pagination/truncation follow-up.

### 2.3 GIE AGSI (storage) and ALSI (LNG) — first real integration

AGSI and ALSI are kept as **separate product identities** (`GIE-AGSI`, `GIE-ALSI`) with separate
normalizers, DB tables and run names. Neither is the IIP product.

* Official contract used (GIE API documentation v013, retrieved 2026-10-10):
  [GIE_API_documentation_v013.pdf](https://www.gie.eu/transparency-platform/GIE_API_documentation_v013.pdf).
  §6.4 example `curl https://agsi.gie.eu/api?type=eu --header "x-key: ..."`; §7.1 parameters
  `page` (starts at 1), `reverse`, `size` (default 30, max 300), `from`, `to`, `date`, `updated`,
  `type` (EU/NE/AI), `country`, `company`, `facility`.
* Envelope fields: `last_page` = pages available for the query; `total` = **entries on this page**
  (not a provider grand total); `dataset`; `gas_day`; `data`.
* Transport: `src/eurogas_nexus/ingestion/gie_transport.py`. Endpoints
  `https://agsi.gie.eu/api` / `https://alsi.gie.eu/api` (`:109-110`). The
  credential boundary is enforced **before send** by `_assert_allowed_endpoint`
  (`:697`): HTTPS only, the product's own host (`GIE_PRODUCT_HOSTS` at `:119`, so
  AGSI can never reach the ALSI host and vice versa), port 443 only, no userinfo,
  the documented `/api` path and no query/fragment. Redirects are disabled
  **per request** in `_request_with_retry` (`:742`,
  `client.send(..., follow_redirects=False)`, overriding any injected client's
  default) and every 3xx raises `GieRedirectRefusedError`, so the `x-key` header
  can never be forwarded to a foreign redirect host. The key is sent only in the
  `x-key` header, never in the URL, and `size` is 1..300 (`:122`, `:470`).
* Untrusted provider text: `error`, `message` and `dataset` bodies are inspected
  in memory only to classify access-denied vs generic provider failure. No raw
  provider text is interpolated into an exception, a chained exception or the
  output; a body that echoes the submitted key cannot leak it
  (`_parse_page` at `:818`). A non-UTF-8 key file raises a stable redacted
  `GieCredentialFileError` with the decoder suppressed (`_read_gie_key_file` at
  `:656`), so credential bytes cannot surface in a traceback.
* Pagination: `fetch_gie_product` (`:494`) keeps page size and page count
  independent and consumes the record budget in **whole pages** (a changing
  `size` would move the provider's page offsets): `max_records=301` fetches one
  300-record page and stops with `stop_reason="operator_record_budget"` /
  `partial_reason="record_budget_whole_page_floor"` -- it does not fetch 600
  records. `max_pages` is clamped to the absolute `GIE_HARD_MAX_PAGES=50`
  (`:124`); a caller cannot raise the hard ceiling. The result reports `records`
  (retained), `record_capacity` (upper bound of the fetched pages) and
  `budget_records` (requested) separately, so a floored budget is never presented
  as the requested one, and `source_reference` (`:366`) states
  `pages=<fetched>/<last_page>` plus `complete=<bool>` and the stop reason. The
  provider's `last_page` still terminates the loop early; `complete`/`stop_reason`
  distinguish the bound, and a budget-limited result is stored as
  `SUCCEEDED_WITH_WARNINGS`, never as full history.
* Envelope validation: `total` must be a non-negative integer equal to `len(data)`;
  a non-empty page must advertise `last_page >= 1`; the requested page must not
  exceed `last_page`; and `len(data)` must not exceed the requested `size`.
  Overlapping natural keys are refused both within a page and across pages (not
  only an exactly repeated page signature), and a changed `last_page` aborts with
  `GiePaginationError`. An unchanged `last_page` is **not** treated as proof of a
  single provider snapshot: GIE exposes no revision/snapshot token, so a silently
  rewritten earlier page is not detectable here. That limitation is deliberate and
  documented rather than hidden.
* Explicit failures: missing credential (`GieCredentialMissingError`), a
  non-official/plaintext/cross-product endpoint (`GieEndpointRefusedError`,
  raised before send), a 3xx (`GieRedirectRefusedError`), 401/403
  (`GieAuthenticationError`), 429 (`GieRateLimitedError`), other HTTP (`GieHttpError`), timeout
  (`GieTimeoutError`), malformed/missing keys (`GieMalformedResponseError`), empty data
  (`GieEmptyResponseError`), cross-product fields (`GieProductMismatchError`), page-sequence or
  overlap problems (`GiePaginationError`), truncation
  (`GieTruncationError`). No synthetic substitute is ever produced.
* Credential precedence: `GIE_API_KEY` → `GIE_API_KEY_FILE` (path from
  `src/eurogas_nexus/core/config_contract.py`, a secret file outside the repo) → encrypted
  `provider_credentials` store (`gie_transport.py:379`, `scripts/ops/ingest_public_sources.py:738`).
  The key is held in a `repr`-suppressed dataclass (`:288`) and never appears in a message or log
  line; an unreadable or non-UTF-8 key file is a stable redacted configuration error, not a
  decoder traceback; tests assert redaction.
* Receipt time: each page carries `received_at_utc` captured **after** the response arrives
  (`fetch_gie_page` at `gie_transport.py:422`, `fetch_gie_product` at `:494`); the script archives the
  raw payload per page with that receipt and the page's record count
  (`scripts/ops/ingest_public_sources.py:412-460`). This corrects the pre-request
  `received_at=started` defect on this path. Other routes still use the pre-request instant (see §4,
  follow-up).
* Multi-page aggregates: `GieConnector.fetch` uses the **last** page's post-response receipt for the
  aggregate payload's `retrieval_ts_utc` (conservative latest retrieval time, never the first page's),
  and `source_reference_id` states `pages=<fetched>/<last_page>;complete=<bool>;stop=<reason>` so a
  bounded partial can never be read as full history. `page_size` and `max_pages` are independent
  constructor inputs (`page_size=30, max_pages=2` fetches two 30-record pages; it no longer collapses
  into one 60-record page), and `max_pages` is clamped to the hard ceiling
  (`connectors/gie.py:77-92`, `:150-158`).
* Normalizers: `gie_storage_observations_from_json` (`public_sources.py:485`) and
  `gie_lng_observations_from_json` (`:564`). The CAM gas-day calendar owns period boundaries. The live
  provider sends `updatedAt` **without an offset**, which the M1-P0 contract refuses to read as UTC; the
  normalizers now accept a receipt instant and, only when the provider stamp is unprovable, use it while
  recording `availability_basis="response_receipt"` and `provider_updated_at_zone="unproven"`. A caller
  with no receipt still gets the original refusal (`:637`). The provider stamp is preserved verbatim in
  `metadata_json.updatedAt`.
* Idempotency: natural key is `product + code + gas day`, so duplicate/revised rows collapse to one
  observation and re-runs preserve first-seen `observed_at_utc`
  (`db/repositories/public_ingestion_upsert.py:34-41`). PostgreSQL-backed persistence tests
  (`tests/integration/test_public_ingestion_upsert_postgres.py`, run against a throwaway schema)
  prove that a new receipt on every poll churns `metadata_json` but does not create a second row and
  does not rewrite the first-seen instant, for both AGSI and ALSI.
* Temporal limitation (explicit): the observation tables hold **one row per natural key and no
  per-observation revision/history row**. A genuinely revised provider value overwrites the row and
  is visible only in the changed value plus the revised provider stamp; `observed_at_utc` stays
  first-seen. Because availability metadata is stored in the same single `metadata_json`, it follows
  the **latest** poll (`availability_basis` can move from `response_receipt` to
  `provider_updated_at`) while `observed_at_utc` remains the first-seen instant. That mixing is a
  schema limitation, not per-poll availability history; modelling revisions/availability per poll
  needs a reviewed schema change and is an explicit follow-up (§6).
* No-mock guard: the GIE branch runs `_reject_synthetic_gie_rows`
  (`scripts/ops/ingest_public_sources.py:805`) before upsert; a `mock-`/`sim-` observation id, a
  `simulated`/`mock` metadata flag or a non-`GIE` source system fails the run. `GieConnector` no longer
  inherits `MockConnector` (`connectors/gie.py:53`) and raises `GieCredentialMissingError` instead of
  returning an empty payload.
* Gates retained: entitlement + certification are unchanged
  (`CERTIFICATION_REQUIRED_SOURCES` at `:79`; `_gate_blockers` at `:598`). HTTP 200 is not
  certification evidence and no certification row was created.
* Default: registry `src-gie` schedule DAILY 09:00 Europe/Brussels with `enabled_default=False`
  (`registry.py:95-116`); the worker path is opt-in. `--limit` defaults to 20 records, so the default
  run is a 1-page bounded partial (`scripts/ops/ingest_public_sources.py:119`).
* High-frequency option: none documented for these products (gas-day granularity).
* Compatible fallback: **unavailable** — no equivalent lawful fallback exists; absent means explicitly
  unavailable, never synthetic.
* Rights: GIE account terms require credit/attribution for use or republication; data is
  export-restricted research-only in this repository. Redistribution review remains open.
* Live-tested (read-only) 2026-10-10, one page per product, no DB:
  * `agsi.gie.eu/api?type=eu&page=1&size=30` → HTTP 200, `dataset=EU`, `last_page=193`,
    `total=30`, 30 records; 30/30 normalized, 0 skipped; all five unit fields populated on all rows;
    availability basis `response_receipt` ×30; period range 2026-09-10T04:00Z → 2026-10-09T04:00Z.
  * `alsi.gie.eu/api?type=eu&page=1&size=30` → HTTP 200, `dataset=EU`, `last_page=180`,
    `total=30`, 30 records; 30/30 normalized, 0 skipped; `inventory`/`sendOut`/`dtmi` populated on
    all rows.
  * Evidence: `.dnx-out/real-sources-20261010/provider-probe-20261010.json`,
    `provider-probe-auth-20261010.json`, `provider-normalize-conformance-20261010.json`.
  * Reviewer-correction probe 2026-10-10 (after the credential-boundary tests passed), using the
    corrected transport, **one page per product**, no DB, aggregate metadata only
    (`.dnx-out/real-sources-20261010/probe_gie_review_fix.py`,
    `provider-probe-review-fix-20261010.json`): AGSI `page=1&size=30` → HTTP 200, `dataset=EU`,
    `total=30 == len(data)=30`, `last_page=192`, 30 records, `complete=false`,
    `stop_reason=operator_record_budget`, `partial_reason=record_budget_whole_page_floor`; ALSI
    `page=1&size=30` → HTTP 200, `dataset=EU`, `total=30 == len(data)=30`, `last_page=180`, 30
    records, same bounded-stop metadata. The advertised `last_page` moves with the gas-day roll
    (193 → 192 between the two same-day probes), which is exactly why it is reported per run rather
    than cached as a constant.
  * Bad/missing key returns **HTTP 200** with `{"error":"access denied","dataset":"storage ERROR"
    |"lng ERROR","message":"Invalid or missing API key"}` (bounded probe). The transport classifies
    this as an authentication failure; a 200 alone is never treated as success, and the body text is
    never echoed into an exception.
* Exact blocker to live ingestion: the fail-closed certification gate
  (`domain/ingestion/certification.py:97-127`) requires a persisted `live_validated`/`certified`
  record carrying `simulated_shape_match` + `live_sample_validation`, which no worker writes. Until an
  operator records it, the route is blocked and reported as a failed run. Attribution/redistribution
  review and pagination-scale decisions (default budget = 1 page) are also open.
* IIP: excluded from this slice. The public `https://iip.gie.eu/json` feed embeds REMIT XML with a
  conflicting outer `date_published` versus inner `publicationDateTime` and defaults to today, not full
  history; this key does **not** imply IIP entitlement. The gap stays explicit.

### 2.4 EEX

* Registry: licensed, freshness 1 minute (`source_registry.py:192-199`).
* Real code: only `ingestion/eex_ngp.py`, a pure parser of the public TTF NGP 15-minute CSV
  (`:70-71`, `parse_eex_ttf_ngp_csv` at `:234`); it performs no network I/O, writes nothing and has no
  scheduler caller. `connectors/eex.py:17` is still a `MockConnector` shell.
* Market Data Hub: the observed website paths are not a supported commercial API contract; transport,
  parameters and schema are unverified (`docs/release/acceptance/COMMERCIAL_CONNECTOR_PROTOCOL_GAPS.md`).
* Cadence vs delay: the official FAQ states intraday prices have a **15-minute delay**; a 1-minute poll
  interval must not be labelled minute-latency, and the registry `freshness_expectation_minutes=1` is a
  target, not the provider's market latency.
* Compatible fallback: the Hub is the owner-requested default/fallback, but no transport exists and
  redistribution rights are not established by public page access.
* Status: parser only; not customer-ready. Exact blockers: no documented transport implemented, no
  OpenAPI/contract, 15-minute delay disclosure, redistribution rights.

### 2.5 ICE_OCM, Trayport, Weather

* All three are `MockConnector` shells with no adapter and no call site
  (`connectors/ice_ocm.py:17`, `connectors/trayport.py:17`, `connectors/weather.py:17`).
* Exact blockers: ICE Data Services subscription/product selection; Trayport protocol/SDK; an actual
  weather provider and contract. Compatible fallback: unavailable.

### 2.6 Platts, ICIS, Argus, Kpler

* Registry rows and credential-placeholder entries only (`source_registry.py:255-298`;
  `api/routes/public/credentials.py:20-40`). No fetch code exists.
* ICIS has a simulated counterpart (`ICIS_Sim`) generated by `simulated_market_prices.py`; simulation
  is not coverage.
* Exact blocker: no supplier contract/adapter. Compatible fallback: unavailable.

### 2.7 Tariff TSOs (NationalGasNTS, BBL, IUK, GTS, NaTran, GermanTSO, FluxysBelgium, CNMCEnagas)

* Registry rows with the shared public-HTTP tariff override (`registry.py:31-37,117-124`).
* `tso_tariffs` (`db/models/route_cost.py:24-54`) has **no production fetch writer**; only the
  development seed writes rows (`scripts/ops/seed_preview_runtime_data.py:159`).
* National Gas discovery: REST-only, SOAP retired June 2026, entry flows sampled every 2 minutes and
  published in 12-minute batches (`COMMERCIAL_CONNECTOR_PROTOCOL_GAPS.md`). Sampling ≠ availability.
* Exact blocker: no documented REST contract retrieved/implemented; tariff documents are manual
  extraction with `manual_review_required`.

### 2.8 Simulated sources (development/test only)

* `EEX_Sim`, `ICE_OCM_Sim`, `Trayport_Sim`, `ICIS_Sim` (`source_registry.py:201,222,243,273`), generated
  by `src/eurogas_nexus/ingestion/simulated_market_prices.py`, gated by
  `EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES` which is force-disabled in trial/release
  (`core/config.py:236-250`). Rows are labelled by `_Sim` source system, `sim:` source reference,
  `sim-` observation id, `simulated_*` freshness and `metadata_json.simulated=True`.
* These are **not customer-deliverable**. Historical simulated rows are retained; this task deletes none.

## 3. Ingestion / worker / scheduler route map

* `scripts/ops/ingest_public_sources.py` is the single live ingestor:
  routes `all, ecb, entsog, entsog-capacity, entsog-reference, gie-agsi, gie-alsi`
  (`:111-132`); `--limit` default 20 (`:119`).
* `scripts/ops/run_public_ingestion_worker.py` loops the ingestor (`:51-57`) at a required interval
  ≥60 s (`:81`), limit default 10000 (`:75`).
* `scripts/ops/run_dataops_scheduler.py` maps `src-ecb → ecb`, `src-entsog → entsog,
  entsog-capacity, entsog-reference`, `src-gie → gie-agsi, gie-alsi` (`:31-35`) and launches the same
  script without `--limit` (`:60-63`), so scheduler runs use the 20-record default.
* Cadences (`domain/dataops/registry.py`): ECB DAILY 16:10 Europe/Berlin; ENTSOG INTERVAL 3600 s;
  GIE DAILY 09:00 Europe/Brussels with `enabled_default=False`. Only these three are `schedulable`.
* No other scheduler exists (no APScheduler/Celery/cron in the tree).
* `deploy/runtime/compose.yaml` exposes ingestion behind opt-in profiles; `simulated-prices` is a
  separate profile service.

## 4. Non-registry ingestion and operator/file routes

* Cost observations: `scripts/ops/refresh_cost_observations.py` → `JsonCostObservationConnector`
  (`ingestion/connectors/cost_source.py:81-127`) → `cost_observations`. No entitlement/certification
  gate, no raw archive, no retry, no scheduler caller. The `cost_source.py` skeletons return `()`
  (`:55-58`).
* EEX NGP: operator-supplied CSV parser only (`ingestion/eex_ngp.py`), writes nothing.
* Seeds: `scripts/ops/seed_preview_runtime_data.py` (local test only, env-gated) and
  `scripts/uat/seed_declared_payment_uat_fixture.py` (isolated UAT DB, explicit acknowledgement).
* `operator-input` is a labelling convention (`governance/entitlement.py:48`; `domain/observations/*`
  defaults), not a registered source. No file-upload/import route exists.

## 5. Customer simulation exclusion status

* Present: the deployment-bundle allow-list (`scripts/release/package_deployment_bundle.policy.json`)
  excludes tests, env files and databases and ships only ten files; `simulated_sources_allowed()`
  forces simulation off in trial/release; the new GIE path has an inline guard (§2.3).
* Missing (mandatory next slice): no CI/release gate scans an image, artifact or database for simulated
  rows, fixture rows or mock payloads; the API image copies the whole `scripts/` tree
  (`deploy/runtime/Dockerfile.api:44`) including seed and simulation scripts; the compose file still
  defines `preview-seed` and `simulated-prices` services. No release-ready or customer-ready claim is
  made.

## 6. Explicit follow-ups (mandatory next slice)

1. ENTSOG pagination/truncation semantics; add a raw archive to the capacity path.
2. Replace the remaining pre-request `received_at=started` archive timestamps on the ECB/ENTSOG routes.
3. EEX Market Data Hub transport/default-fallback with explicit product, currency, unit, delivery
   interval, quote basis and freshness; disclose the 15-minute intraday delay; resolve redistribution.
4. National Gas REST contracts (2-minute sampling / 12-minute publication) and Fluxys EDP review.
5. ICE_OCM / Trayport / Weather / Platts / ICIS / Argus / Kpler supplier contracts and adapters.
6. Certification/attribution procedure for GIE so live ingestion can pass the existing gate; IIP
   timestamp-semantics clarification before any IIP work.
7. Artifact/DB simulation-exclusion gate and removal of dev seed/simulation services from the customer
   deployment path.
8. Operator-set GIE page budget review (default is one page; full history is ~192 AGSI pages at probe
   time and moves with the gas-day roll).
9. Observation revision/availability modelling: the observation tables are single-row-per-natural-key
   with no per-observation revision or per-poll availability record, so a revised value overwrites in
   place and `metadata_json.availability_basis` describes the latest poll while `observed_at_utc`
   stays first-seen. A reviewed schema/ADR change is required before any revision-history claim.

## 7. Verdict

* Registry reconciliation: **24/24 accounted for**; no registry source is silently treated as live.
* Real transports: ECB, ENTSOG, GIE (GIE newly real, protocol-tested and live-tested read-only).
* All-source coverage remains **incomplete**: 0 customer-ready sources, 3 real fetch paths, 3 sources
  whose only code is a mock shell, 12 registry-only sources and 4 simulated generators. Nothing here
  is production or redistribution approval.
* Reviewer corrections (2026-10-10) are implemented and regression-tested: credential boundary
  (endpoint validation + per-request redirect refusal), untrusted provider-text redaction, whole-page
  record budgets with an absolute page ceiling and envelope/overlap validation, honest multi-page
  connector aggregates, and real PostgreSQL upsert persistence tests.
* Customer-ready sources: **0**. Customer-ready is not claimed and cannot be claimed until rights,
  certification for GIE and the artifact-exclusion gate are resolved.
