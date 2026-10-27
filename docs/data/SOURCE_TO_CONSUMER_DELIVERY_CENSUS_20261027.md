# Source-to-consumer delivery census — 2026-10-27

Status: **audit only, not delivery acceptance.** This census records what the current
checkout actually implements for every registered data source, from downloader/parser to
persistence and API/SDK/Web consumers. It does not activate a source, change a grant or
certification, read a credential, contact a provider, or query a database.

**Findings.** No registered source reaches full lawful source-to-consumer business
acceptance in this checkout. Three source families have a real provider HTTP code path
(ECB, ENTSOG, GIE); one has a real parser but no production persistence path (EEX TTF NGP);
three TSO tariff datasets exist only as manually transcribed development seed data
(National Gas NTS, BBL, IUK); four `*_Sim` sources are synthetic; the remaining registered
sources are catalog, mock-shell or empty-API entries. Fixture and `httpx.MockTransport`
tests prove adapter semantics only. No fresh live provider, entitlement, certification or
browser journey is established here.

## 1. Method and limits

Inspected: `docs/engineering/Architecture-V2/CODEX_ENTRYPOINT.md`,
`docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`,
`docs/release/acceptance/23_DELIVERY_RECOVERY_AND_GATES.md`,
`docs/product/DATA_OPERATIONS_SPEC.md`, the source contracts, the source registry, typed
data-operations registry, ingestion/connector/transport modules, persistence calls, public
API routes, Python SDK modules, Web API client/source-center modules, and the focused test
modules cited in section 6.

Execution limitation: the shell failed before running with an ACL lock error
(`Win32 5`, `dsh-acl-locks`); `grep` and `glob` also failed to launch. Per instruction I did
not retry or modify ACLs. Therefore **no tests were run**, no dependency was installed and
no database or network probe was made. Findings below are from direct file inspection. Test
modules are cited as evidence of written coverage, not as a fresh pass claim.

No secret value was read. The GIE credential path/state was inspected only as code and
configuration logic, never as a secret.

## 2. Registry as found (not assumed)

`src/eurogas_nexus/domain/ingestion/source_registry.py::registered_sources` returns **24**
records. Counts observed in that file: 11 `price`, 8 `tariff`, 2 `infrastructure`, 1 `fx`,
1 `weather`, 1 `ai`. Ten are marked licensed/credential-required; fourteen are marked public.
Every static record starts `certification_stage="unverified"` and
`certification_allows_live=False`.

`src/eurogas_nexus/domain/dataops/registry.py::source_definitions` derives the operational
view. Only `src-ecb`, `src-entsog` and `src-gie` are `schedulable=True`. The production
scheduler runner in `scripts/ops/run_dataops_scheduler.py::_SOURCE_ARGS` has a command
mapping only for those same three source IDs. `src-eex`, `src-ice-ocm`, `src-trayport`,
`src-platts`, `src-icis`, `src-argus`, `src-kpler`, `src-weather`, all eight tariff IDs and
`src-deepseek` have no production runner.

| Category | Source IDs (exact) |
| --- | --- |
| FX (1) | `src-ecb` |
| Infrastructure (2) | `src-entsog`, `src-gie` |
| TSO tariff (8) | `src-national-gas-nts`, `src-bbl`, `src-iuk`, `src-gts`, `src-natran`, `src-german-tso`, `src-fluxys-belgium`, `src-cnmc-enagas` |
| Price / licensed (7) | `src-eex`, `src-ice-ocm`, `src-trayport`, `src-platts`, `src-icis`, `src-argus`, `src-kpler` |
| Price / simulated (4) | `src-eex-sim`, `src-ice-ocm-sim`, `src-trayport-sim`, `src-icis-sim` |
| Weather (1) | `src-weather` |
| LLM (1) | `src-deepseek` |

## 3. Chain and evidence codes

**Chain codes**

| Code | Actual chain |
| --- | --- |
| `C-ECB` | `scripts/ops/ingest_public_sources.py::ECB_DAILY_URL`, `_fetch_text` → `public_sources.ecb_market_observations_from_xml` / `ecb_fx_observations_from_xml` → `upsert_observation_rows` → `MarketObservationRecord` + `FxObservationRecord` → `/api/market/observations`, `/api/market/fx` → SDK `market.py` → Web `api.marketObservations`, `api.fxRates`. |
| `C-ENTSOG` | `ingestion/entsog_transport.py::fetch_entsog_dataset` → `ingestion/entsog_ingestion.py::archive_entsog_pages`, `persist_entsog_observations`, `persist_entsog_reference` → `FlowObservationRecord`, `CapacityObservationRecord`, `ReferenceNode`, `ReferenceFacility`, `ReferenceMarketHub`, `ReferenceTsoAccessPoint` → `/api/physical/flows`, `/api/physical/capacity`, `/api/reference-network/*` → SDK `physical.py` / `reference_network.py` → Web `api.flowObservations`, `api.capacityObservations`, `api.nodes`, `api.facilities`, `api.tsoAccess`. |
| `C-GIE` | `ingestion/gie_transport.py::fetch_gie_product` (HTTPS, `x-key`, bounded pages) → `ingest_public_sources.py::_persist_gie_product` / `upsert_revision_safe_observation_rows` → `StorageObservationRecord` / `LngObservationRecord` → `/api/storage/*`, `/api/lng/*` → SDK `storage.py` / `lng.py` → Web `api.storageObservations`, `api.lngObservations`. |
| `C-EEX-PARSE` | `ingestion/eex_ngp.py::parse_eex_ttf_ngp_csv`, `eex_ttf_ngp_market_observations`; `ingestion/eex_ngp_capture.py::inspect_eex_ngp_capture`; CLI `scripts/ops/inspect_eex_ngp_capture.py`. No downloader, no ingest-script branch, no scheduler runner, no persistence caller. |
| `C-SIM` | `ingestion/simulated_market_prices.py::upsert_simulated_market_observations` → `MarketObservationRecord`, `MarketQuoteRecord`, `IngestionRunRecord`, intraday opportunity scan → `/api/market/*` → SDK `market.py` → Web `api.marketObservations`, `api.marketQuotes`. |
| `C-MANUAL-TARIFF` | `domain/route_cost/uk_public_tariffs.py` (National Gas NTS), `domain/route_cost/european_public_tariffs.py` (BBL/IUK) → `scripts/ops/seed_preview_runtime_data.py::_seed_public_tariffs` → `TsoTariffRecord` → `/api/route-cost/tso-tariffs` and route-cost composition → SDK `route_cost.py::RouteCostTariff` → Web `api.tsoTariffs`. |
| `C-COST-JSON` | `ingestion/connectors/cost_source.py::JsonCostObservationConnector` → `application/cost_source_refresh.py::refresh_cost_source` → `CostObservationRecord` → `/api/cost-observations/*` → SDK `cost_observations.py`. Requires an operator-supplied URL; no official provider endpoint is built in. |
| `C-MOCK` | `ingestion/connectors/base.py::MockConnector`: returns an empty payload, never calls a provider. Used for ECB, ENTSOG, EEX, ICE OCM, Trayport and Weather shells. GIE is the exception (real connector). |
| `C-CATALOG` | Registry + credential provider row only; no adapter, persistence or observation API. |
| `C-EMPTY-API` | Route returns an explicit empty envelope; no runtime source or persistence model behind it. |
| `C-LLM` | Credential + connection test for `DEEPSEEK`/`LLM`; not a market-data ingestion source. |

**Test codes**

| Code | Test module | What it proves / does not prove |
| --- | --- | --- |
| `T1` | `tests/ingestion/test_public_source_ingestion.py` | ECB, ENTSOG and GIE normalizers on fixtures; no live network. |
| `T2` | `tests/ingestion/test_source_timezone_contract.py` | Exact CET/CEST/UTC/DST timezone cases and refusals; no provider call. |
| `T3` | `tests/ingestion/test_entsog_transport.py` | ENTSOG pagination/offset/sort/envelope behavior with `httpx.MockTransport`; no live API. |
| `T4` | `tests/ingestion/test_entsog_window.py` | Calendar/rolling-window selection and DST cases; no provider or DB. |
| `T5` | `tests/ingestion/test_gie_transport.py` | GIE credential boundary, host/redirect rules, envelope and pagination with mock transport; no live API. |
| `T6` | `tests/ingestion/test_eex_ngp_csv.py` | EEX NGP parser and canonical-mapping gates on synthetic CSV; no downloaded value. |
| `T7` | `tests/ingestion/test_eex_ngp_capture.py` | Byte hashing, local-file inspection, CLI refusals; no network or DB. |
| `T8` | `tests/ingestion/test_simulated_market_prices.py` | Simulated observation/quote shape and persistence path; synthetic rows only. |
| `T9` | `tests/api/test_sources_api.py` | Source catalog, family grouping and simulated posture; it does not prove a live source. |
| `T10` | `tests/api/test_route_cost_api.py` | Tariff/route reads, including empty non-DB behavior and hardcoded published tariff rows. |
| `T11` | `clients/web/tests/sourceRegistryRead.test.ts` | Source Center pending/failed/empty read states; no browser journey. |

**Gate codes**

| Code | Gate |
| --- | --- |
| `G1` | Every static source starts `certification_stage="unverified"`, `certification_allows_live=False`. |
| `G2` | `CERTIFICATION_REQUIRED_SOURCES` in `ingest_public_sources.py` = ENTSOG, GIE, GIE-AGSI, GIE-ALSI; `_gate_blockers` also enforces entitlement and source runtime state. |
| `G3` | GIE requires `GIE_API_KEY`, `GIE_API_KEY_FILE` or the encrypted store; operator-disabled credential/source is authoritative; redirects refused. |
| `G4` | Licensed market/weather sources require credentials and certification; only GIE and DEEPSEEK/LLM have a backend connection test (`CONNECTION_TEST_PROVIDERS`). |
| `G5` | Simulated sources require development/test configuration and are not customer-delivery data. |
| `G6` | The tariff seed is explicitly local PostgreSQL test data and refuses non-simulated trial/release environments. |
| `G7` | EEX NGP canonical mapping needs two independent evidences: publication timezone and delivery gas-day calendar; neither is proven. |
| `G8` | No production runner exists outside `src-ecb`, `src-entsog`, `src-gie`; a queued run for another source fails `CONFIGURATION` (`No production runner is implemented for ...`). |
| `G9` | Weather has no selected governed provider, protocol or rights record in the inspected code. |

## 4. Per-source census

### 4.1 Real provider HTTP code paths

| Source ID / system | Datasets found | Chain and consumers | Tests | Gate | Missing / next |
| --- | --- | --- | --- | --- | --- |
| `src-ecb` / ECB / FX, public | `eurofxref-daily`, `fx-reference-rates` | `C-ECB`; real HTTPS XML, normalizer writes market + FX tables; `/api/market/observations`, `/api/market/fx`, normalized view; SDK `market.py`; Web `api.marketObservations`, `api.fxRates`. | `T1`, `T9` | None beyond normal auth; public reference rates. | Code-real but no fresh live proof in this checkout; no browser/FX-value acceptance. Source Center count is DB-derived. |
| `src-entsog` / ENTSOG / Infrastructure, public but export-restricted | `connection-points`, `operator-directions`, `flows`, `capacity`, `outages`, `ip` | `C-ENTSOG`; real HTTPS offset traversal for `operationaldatas`, `connectionpoints`, `operatorpointdirections`; raw archive; flows/capacity/reference persistence; `/api/physical/flows`, `/api/physical/capacity`, `/api/reference-network/*`; SDK `physical.py`, `reference_network.py`; Web `api.flowObservations`, `api.capacityObservations`, `api.nodes`, `api.facilities`, `api.tsoAccess`. | `T1`–`T4`, `T9` | `G2` (ENTSOG certification required) plus runtime disable and entitlement. | `outages` is **not** in `ENTSOG_DATASETS`, and `/api/physical/outages` is a hardcoded empty envelope (`physical.py::list_outages`); no separate `ip` dataset fetch path was found either. `src-entsog` connector shell is still `MockConnector` even though the script path is real. Snapshot consistency is explicitly unproven. No fresh live/certification proof. |
| `src-gie` / GIE / Infrastructure, licensed | `agsi-storage`, `alsi-lng` | `C-GIE`; real keyed HTTPS, per-product host/path validation, redirect refusal, page-envelope checks, revision-safe persistence; `/api/storage/*`, `/api/lng/*`; Web DTOs aligned; SDK DTOs **not** aligned (section 5). | `T1`, `T2`, `T5`, `T9` | `G2` + `G3`: key, entitlement, certification, operator disable. | Live path exists but no fresh keyed acceptance, no certification evidence. Typed SDK cannot consume the actual storage/LNG payloads. Bound is per product/page; complete history is not claimed. |

### 4.2 Licensed market data and synthetic substitutes

| Source ID / system | Datasets found | Chain and consumers | Tests | Gate | Missing / next |
| --- | --- | --- | --- | --- | --- |
| `src-eex` / EEX / Exchange, licensed | `gas-futures`, `gas-spot`, `screen-trades`, `settlements`; NGP parser declares `ttf-ngp-15min` but that dataset is not in the source registry | `C-EEX-PARSE` plus `C-MOCK`. Parser/capture inspector can validate an operator file, but no HTTP download, no `ingest_public_sources` branch, no scheduler runner, no persistence caller and no API/SDK/Web consumer of NGP rows were found. | `T6`, `T7` | `G4` + `G7` + `G8`; EEX certification unverified, no entitlement/certification. | Two independent evidence blockers: official `Timestamp Let` zone and official `Gasday` delivery calendar. Registry datasets differ from parser (`ttf-ngp-15min` not registered). No EEX Market Data Hub or futures/spot adapter. |
| `src-eex-sim` / EEX_Sim / Simulated | `gas-spot`, `day-ahead`, `weekend`, `month-ahead`, `simulated` | `C-SIM`; writes `MarketObservationRecord`, `MarketQuoteRecord`, runs and opportunities; `/api/market/*`; Web/SDK. Source API marks EEX as `active_simulated` when rows exist. | `T8`, `T9` | `G5`; development/test only. | Synthetic only; never customer/licensed evidence. It is a preview substitute, not a fallback for production rights. |
| `src-ice-ocm` / ICE_OCM / Exchange, licensed | `within-day`, `day-ahead`, `screen-orders`, `live-marks` | `C-MOCK` only. No downloader, parser, persistence or live-test route; credential provider row exists. | `T9` only (catalog posture) | `G4` + `G8`. | No ICE OCM protocol/interface, no entitlement/certification. Real screen-order path exists as a model/API (`ScreenOrderObservationRecord`) but no licensed loader. |
| `src-ice-ocm-sim` / ICE_OCM_Sim / Simulated | `within-day`, `day-ahead`, `screen-marks`, `simulated` | `C-SIM`; market observations/quotes and Web/SDK. | `T8` | `G5`. | Synthetic only. |
| `src-trayport` / Trayport / Broker, licensed | `broker-screens`, `market-data`, `screen-orders` | `C-MOCK` only; credential row exists. | `T9` only | `G4` + `G8`. | No socket/HTTP protocol, no entitlement/certification. Real broker screen feed absent. |
| `src-trayport-sim` / Trayport_Sim / Simulated | `broker-screens`, `within-day`, `day-ahead`, `simulated` | `C-SIM`; market observations/quotes. | `T8` | `G5`. | Synthetic only. |
| `src-platts` / Platts / Licensed assessment | `assessments`, `forward-curves`, `indices` | `C-CATALOG`; credential row only. No adapter, persistence or observation route. | `T9` only | `G4` + `G8`. | No licensed assessment adapter or rights evidence. |
| `src-icis` / ICIS / Licensed assessment | `heren-assessments`, `day-ahead`, `indices`, `curves` | `C-CATALOG`; no real adapter. `src-icis-sim` is the only ICIS-shaped data path. | `T9` only | `G4` + `G8`. | No real ICIS feed; simulated daily assessment must not be presented as licensed ICIS data. |
| `src-icis-sim` / ICIS_Sim / Simulated | `heren-assessments`, `day-ahead`, `daily-assessment`, `simulated` | `C-SIM`; daily assessment rows in market observations. | `T8` | `G5`. | Synthetic only. |
| `src-argus` / Argus / Licensed assessment | `assessments`, `indices`, `curves` | `C-CATALOG`; credential row only. | `T9` only | `G4` + `G8`. | No adapter, entitlement or certification. |
| `src-kpler` / Kpler / Licensed LNG/market intelligence | `lng-flows`, `cargo-tracking`, `market-data` | `C-CATALOG`; credential row only. | `T9` only | `G4` + `G8`. | No cargo/flows adapter; no cargo-slot persistence. |

### 4.3 TSO tariffs

| Source ID / system | Datasets found | Chain and consumers | Tests | Gate | Missing / next |
| --- | --- | --- | --- | --- | --- |
| `src-national-gas-nts` / NationalGasNTS / Tariff, public | `transportation-statement`, `entry-tariffs`, `exit-tariffs`, `commodity-charges` | `C-MANUAL-TARIFF`; hardcoded published rows in `uk_public_tariffs.py`; `TsoTariffRecord`; `/api/route-cost/tso-tariffs`; route-cost composition; SDK/Web. | `T10` (read/route behavior) | `G6`; no live fetch. | No downloader or parser for the publication in the inspected paths; data only exists after the development seed. Customer artifact excludes the seed; no supported customer import path. |
| `src-bbl` / BBL / Tariff, public | `interconnector-tariffs`, `forward-flow`, `reverse-flow` | `C-MANUAL-TARIFF`; two hardcoded BBL rows; same persistence/API/SDK/Web chain. | `T10` | `G6` | Same as NTS: manual transcription, no live adapter, no customer seed. |
| `src-iuk` / IUK / Tariff, public | `interconnector-tariffs`, `bacton`, `zeebrugge` | `C-MANUAL-TARIFF`; four hardcoded IUK rows; same chain. | `T10` | `G6` | Same as NTS: manual transcription, no live adapter, no customer seed. |
| `src-gts` / GTS / Tariff, public | `netherlands-transmission-tariffs`, `entry-exit` | `C-CATALOG`; source filter exists in `/api/sources`; no source-specific dataset module found, no persistence writer. | `T9` only | `G6` not applicable; no adapter | Source appears in catalog and count query, but no GTS tariff data path. |
| `src-natran` / NaTran / Tariff, public | `france-transmission-tariffs`, `entry-exit`, `peg` | `C-CATALOG`; source filter exists; no dataset module or writer found. | `T9` only | None implemented | No NaTran/GRTgaz/Terega data path. |
| `src-german-tso` / GermanTSO / Tariff, public | `germany-transmission-tariffs`, `the-market-area`, `entry-exit` | `C-CATALOG`; source filter exists; no dataset module or writer found. | `T9` only | None implemented | No German TSO data path. |
| `src-fluxys-belgium` / FluxysBelgium / Tariff, public | `belgium-transmission-tariffs`, `ztp`, `interconnection` | `C-CATALOG`; source filter exists; no dataset module or writer found. | `T9` only | None implemented | No Fluxys Belgium data path. |
| `src-cnmc-enagas` / CNMCEnagas / Tariff, public | `spain-access-tolls`, `transmission`, `regasification` | `C-CATALOG`; source filter exists; no dataset module or writer found. | `T9` only | None implemented | No CNMC/Enagas data path. |

The generic `C-COST-JSON` framework is not a substitute for these eight sources. It takes any
operator URL, has no official provider mapping, returns `()` on non-200, and
`_cost_observation_from_json` turns a missing `value` into `0.0` (`float(record.get("value")
or 0.0)`). That is a zero-fabrication risk for route-cost inputs and must not be certified as
a TSO tariff feed.

### 4.4 Weather and model provider

| Source ID / system | Datasets found | Chain and consumers | Tests | Gate | Missing / next |
| --- | --- | --- | --- | --- | --- |
| `src-weather` / Weather / Licensed, keyed | `temperature`, `hdd`, `cdd`, `forecast` | `C-MOCK` plus `C-EMPTY-API`: `/api/weather/stations`, `/api/weather/observations`, `/api/weather/hdd-cdd` all return static empty data with `WEATHER_SOURCE_NOT_CONFIGURED`; SDK `weather.py` types exist; no persistence model or ingestion path found. | `T9` only | `G4` + `G9`; no provider/protocol/rights decision. | Open-Meteo/Copernicus are described only as direction in the simulated-source runbook, not implemented or governed. Do not build a speculative endpoint before the provider/rights decision. |
| `src-deepseek` / DEEPSEEK / Model provider | `analysis`, `reporting`, `qa` | `C-LLM`: credential and connection test; not a market-data source; no observation persistence or `/api/market` path. | Not a data-ingestion test target | `G4`; credential required. | Out of scope for source-to-consumer market data except credential governance. |

## 5. Consumer trace and concrete breakpoints

| Consumer layer | What it actually reads | Status |
| --- | --- | --- |
| Source Center API | `GET /api/sources`, `/api/sources/{id}`, `/api/ingestion-runs`, `/api/sources/{id}/health`, `/runs`; operator writes `/run`, `/backfill`, `/retry`, `/enabled` in `source_operations.py`. | Registry plus DB overlays. Manual `/run` queues a run for **any** source ID; worker executes only `src-ecb`, `src-entsog`, `src-gie` and records `CONFIGURATION` failure for the rest (`G8`). |
| Web Source Center | `clients/web/src/components/SourceCenter.tsx`; `api.sources`, credential provider/connection methods; `sourceRunModel.ts` offers a Run control and discloses credential/circuit/readiness. | It can offer a run that the worker cannot execute. `sourceRunReadiness` blocks only no-source/no-DB/in-flight, not an unsupported runner. |
| Market | `/api/market/observations`, `/fx`, `/quotes`, `/normalized`, `/spreads`, `/opportunities`; `market_reads.py`. | ECB real reference rows and simulated rows are readable. No real EEX/ICE/Trayport/ICIS/Platts/Argus/Kpler rows exist without a licensed adapter. |
| Physical / reference network | `/api/physical/flows`, `/capacity`, `/outages`; `/api/reference-network/*`. | ENTSOG flows/capacity/reference work when ingested and gate-passed. `/outages` is always empty; there is no outage persistence path. |
| Storage / LNG | `/api/storage/sites`, `/observations`; `/api/lng/terminals`, `/observations`. | GIE data can be persisted. Web DTOs match the API (`facility_id`, `inventory_twh`, `terminal_id`, etc.). Typed SDK DTOs do not. |
| TSO tariffs / route cost | `/api/route-cost/tso-tariffs`; `TsoTariffRecord` via `list_tso_tariffs`; route-cost composition; `/api/cost-observations/*`. | Only manually seeded NTS/BBL/IUK rows are usable; the other five tariff sources have no data path. Cost-observation JSON is generic/operator-configured, with a missing-to-zero risk. |
| Weather | `/api/weather/*`. | Always empty; no runtime source, model or consumer data. |

### 5.1 Typed SDK break for GIE data (confirmed contract mismatch)

`packages/python-sdk/src/eurogas_nexus_sdk/storage.py`:

- `StorageSite` requires `site_id`, `name`, `country`, `lat`, `lon`; `/api/storage/sites`
  returns no `lat`/`lon` and returns `working_capacity_twh`, not `working_capacity_mcm`.
- `StorageObservation` requires `site_id`, `site_name`, `observation_type`; the API returns
  `facility_id`, `facility_name`, `inventory_twh`, `working_capacity_twh`, `fill_pct`,
  `injection_twh_d`, `withdrawal_twh_d` and no `observation_type`/`volume_mcm`.

`packages/python-sdk/src/eurogas_nexus_sdk/lng.py`:

- `LngTerminal` requires `lat`/`lon`; `/api/lng/terminals` does not return them.
- `LngObservation` requires `observation_type` and `value_mcm`; the API returns
  `inventory_twh`, `send_out_twh_d`, `dtmi_twh` and no such fields.

Pydantic will therefore raise for real GIE API rows. This is not a fixture issue: it is a
source-to-consumer contract break at the typed boundary. The Web DTOs (`StorageObsDTO`,
`LngObsDTO` in `clients/web/src/api/client.ts`) already use the API field names, so the
browser path is not the broken one. No SDK test found at the inspected paths exercises the
current GIE payload shape.

### 5.2 Source-status semantics that should not be over-read

- `connectivity_status="active"` means DB rows exist and the newest observation is within the
  source expectation; it does not mean the provider was contacted in this audit.
- `operational_status="active_simulated"` explicitly means a licensed source is being
  represented by a `*_Sim` substitute. It is not native connectivity.
- `certification_stage` is "unverified" unless a persisted certification row says otherwise;
  the static default is fail-closed.
- The source read counts only specific tables/systems (`_runtime_source_counts`), and
  `/api/ingestion-runs` maps run `source_name` to a source ID. A missing count is not proof
  that no provider exists; it is proof that no row in the counted table matches.

## 6. Tests and what they do not prove

`T1`–`T11` are real committed test modules, but every provider module inspected uses
`httpx.MockTransport`, hand-built CSV/XML/JSON or in-memory SQLite. They prove:

- parser/normalizer field mapping, timezone refusals and DST handling;
- pagination, sorting, envelope and credential-boundary behavior under controlled responses;
- EEX NGP parse/capture refusals and byte preservation;
- simulated row shape and source catalog/posture.

They do **not** prove:

- a live ECB/ENTSOG/GIE response, current provider schema, latency or entitlement;
- that GIE's key works for AGSI and ALSI separately;
- that a certification record exists or that redistribution is permitted;
- that the SDK can deserialize real GIE rows;
- that a browser workflow renders source data with correct units/values;
- that a customer deployment has any TSO tariff rows or weather rows.

No fresh test count is claimed. Earlier execution-state counts are historical and not
reproduced by this audit.

## 7. Lost-work and recovery-register cross-check

`docs/release/acceptance/23_DELIVERY_RECOVERY_AND_GATES.md` names missing unpublished files.
Direct reads now find several of them present:

- `src/eurogas_nexus/ingestion/eex_ngp_capture.py`
- `scripts/ops/inspect_eex_ngp_capture.py`
- `tests/ingestion/test_eex_ngp_capture.py`
- `src/eurogas_nexus/domain/route_cost/lng_terminal_reference.py`

The recovery register is therefore **stale for those items** (it says the EEX capture files
are absent). Their presence is a reconstructed, locally reviewed implementation, not
restoration of the original cloud work and not evidence of provider rights. The terminal
reference module is informational only: its committed manifest contains candidate facts, not
reviewed facts, terminal rights or availability.

Still absent at the named paths:

- `clients/web/src/app/model/lngEconomicsModel.ts`
- `clients/web/src/components/LngEconomicsPanel.tsx`
- `clients/web/src/styles/lng-economics.css`
- `clients/web/tests/lngEconomics.test.ts`

The source contracts inspected are `docs/data/EEX_NGP_SOURCE_CONTRACT.md` and
`docs/data/SOURCE_TIMEZONE_CONTRACT.md`. The broader current source record is
`docs/product/DATA_OPERATIONS_SPEC.md`. That September specification is stale where this
census differs: GIE now has a real connector/transport (not only a shell), EEX has a local
capture inspector, and the typed scheduler/runner coverage is narrower than "public source
ingestion" implies. No prior document encountered in this inspection performs this
per-source consumer census; this file is the current record.

## 8. Gap matrix and prioritized next slices

| Gap | Affected source IDs | Evidence | Business consequence |
| --- | --- | --- | --- |
| No real licensed market/weather adapter | `src-eex`, `src-ice-ocm`, `src-trayport`, `src-platts`, `src-icis`, `src-argus`, `src-kpler`, `src-weather` | `C-MOCK`/`C-CATALOG`; no transport module | no licensed prices, broker screens or weather/HDD/CDD |
| No production runner | 21 registered IDs outside the three `_SOURCE_ARGS` entries | `G8`; `_SOURCE_ARGS` | operator-triggered runs fail as `CONFIGURATION`, not as a missing capability |
| Typed GIE consumer break | `src-gie` | storage/lng SDK DTOs vs `/api/storage/*`, `/api/lng/*` | Python SDK cannot consume real GIE rows |
| Outages missing end-to-end | `src-entsog` | `ENTSOG_DATASETS` excludes outages; `/api/physical/outages` empty | no maintenance/outage visibility |
| Tariff data dev-only | 8 tariff IDs | `C-MANUAL-TARIFF`, `G6`; five IDs have no data path | customer route costing has no usable tariff rows |
| EEX NGP evidence-gated | `src-eex` | `G7`; `C-EEX-PARSE`; dataset not registered | EEX index cannot be persisted or consumed |
| No fresh live/certification proof | `src-ecb`, `src-entsog`, `src-gie` | `G1`–`G3`; fixture-only tests | no source can be called live-accepted here |
| Weather empty | `src-weather` | `C-EMPTY-API`, `G9` | no HDD/CDD or forecast data |

Ranked by real end-user impact and by whether the work can be done without inventing provider
authority. None of these were executed by this audit.

### P1 — Typed SDK parity for GIE storage/LNG

- **Impact:** the only real licensed live path currently cannot be consumed through the
  documented typed SDK. Any research/report/client script using `fetch_storage_*` or
  `fetch_lng_*` fails on real GIE rows.
- **Bounded work:** align `storage.py`/`lng.py` DTOs to the current `/api/storage/*` and
  `/api/lng/*` payloads (or add explicit field aliases/mapping), and add contract tests that
  feed the actual API row shapes into the SDK models. Preserve `research_only` and
  `source_reference`.
- **Evidence needed:** none external; use the existing API contract.
- **Acceptance:** real-shaped GIE rows deserialize; no fabricated units; Web DTO parity
  remains green; tests cover both sites/observations and terminals/observations.

### P1 — Customer-usable TSO tariff path for one corridor

- **Impact:** route costing is a core workflow, but customer deployments have no tariff rows
  because the only NTS/BBL/IUK data is development seed data. Five further tariff sources
  have no path at all.
- **Bounded work:** pick one publisher already evidenced in code (National Gas NTS or BBL/IUK)
  and implement a reviewed operator import with source document id, effective dates, units,
  `source_refs` and `manual_review_required`; or, if only a PDF is published, make the
  reviewed transcription an explicit operator command with provenance instead of a dev-only
  seed. Do not add an unscoped HTTP endpoint.
- **Evidence needed:** the official publication URL and format already cited in
  `uk_public_tariffs.py` / `european_public_tariffs.py`; confirm current version and effective
  dates. No new speculative endpoint.
- **Acceptance:** a clean customer runtime can load reviewed rows through a supported path;
  `/api/route-cost/tso-tariffs` and route-cost composition return them; the dev seed remains
  test-only.

### P1 — Make Source Center run controls truthful for unsupported sources

- **Impact:** operators can queue `/api/sources/{id}/run` for 21 sources with no runner; the
  worker then records a configuration failure. That looks like a source problem rather than
  a missing implementation.
- **Bounded work:** expose `runner_supported`/`schedulable` in the source read; disable or
  clearly label Run/Backfill/Retry where no runner exists; have the queue route refuse with a
  stable `runner_not_implemented` code instead of queuing a doomed run. Keep manual run
  available for ECB/ENTSOG/GIE.
- **Evidence needed:** none external; `_SOURCE_ARGS` and `source_definitions` are the source
  of truth.
- **Acceptance:** UI and API agree; no unsupported run is persisted as a source failure;
  Source Center tests cover the disabled state.

### P1 — GIE live conformance and certification closure (external evidence)

- **Impact:** GIE is the only licensed live source with a real keyed transport. Without
  actual page conformance and certification it remains unverified for customer use.
- **Bounded work:** using an owner-supplied credential (not read or logged by this audit), run
  the existing bounded AGSI and ALSI connection tests, verify per-product entitlement, record
  `CONNECTION_VERIFIED`/`DATA_VALIDATED` evidence and a certification decision. Do not infer
  one product from the other. Do not activate scheduling without the existing gates.
- **Evidence needed:** GIE API documentation v013 already cited in `gie_transport.py`; actual
  response samples, per-product entitlement, certification record. No new endpoint.
- **Acceptance:** both products independently verified, source health reflects it, SDK path
  works, and a browser storage/LNG workflow renders the same values.

### P2 — ENTSOG outages end-to-end

- **Impact:** the registry advertises outages and the UI exposes `/api/physical/outages`, but
  the endpoint is a hardcoded empty envelope. Maintenance/outage visibility is missing from
  the physical cockpit.
- **Bounded work:** verify the official ENTSOG TP dataset/schema for outages, add it to the
  bounded transport dataset set only after that evidence, archive pages, persist outage rows,
  expose them through the existing physical route, and add fixture/protocol tests.
- **Evidence needed:** official ENTSOG TP API manual v3.0 plus the official outage dataset
  definition (name, fields, time basis). Do not infer from the flows endpoint.
- **Acceptance:** ingested outage rows retain source/receipt/lineage, `/api/physical/outages`
  returns them, and the source gate remains fail-closed.

### P2 — EEX NGP evidence and registration, not speculative download

- **Impact:** the parser and capture inspector are good, but EEX NGP cannot become a product
  input until the two independent contracts are proven and the dataset is registered.
- **Bounded work:** record official EEX evidence for `Timestamp Let` semantics/zone and for
  `Gasday` delivery calendar; register `ttf-ngp-15min` under `src-eex`; then allow an explicit
  operator file import through the capture seam. Do not add a download or schedule until
  rights/certification are resolved.
- **Evidence needed:** official EEX methodology or written operator confirmation. No URL or
  field may be guessed.
- **Acceptance:** canonical rows are produced only with both evidences; source status exposes
  the dataset; no row is written while either evidence is missing.

### P3 — Weather provider decision (do not code yet)

- **Impact:** `/api/weather/*` is always empty, so HDD/CDD and weather-driven analytics have
  no source.
- **Bounded work:** choose a governed provider and rights basis (Open-Meteo is only a
  development direction; Copernicus/ERA5 is an alternative), then implement adapter,
  persistence, API and provenance. Do not register a speculative URL.
- **Evidence needed:** provider terms, attribution/redistribution rights, official API
  documentation. Owner/product decision first.
- **Acceptance:** non-empty weather/HDD/CDD reads with source and period evidence; no
  synthetic weather fallback.

### P3 — Licensed exchange/broker adapters (blocked on contracts)

- `src-eex`, `src-ice-ocm`, `src-trayport`, `src-platts`, `src-icis`, `src-argus` and
  `src-kpler` require licensed interface specifications, credentials, entitlements and
  certification. No adapter should be built from an assumed endpoint. The current simulated
  substitutes remain visibly labelled and are not customer-delivery evidence.

## 9. Acceptance verdict

| Question | Answer from this checkout |
| --- | --- |
| Does every registered source have a real provider adapter? | No. 3 code-real, 1 parser-only, 3 manual tariff datasets, 4 simulated, the rest catalog/mock/empty. |
| Does every real adapter persist and reach API/SDK/Web? | Not cleanly. ECB/ENTSOG do; GIE reaches API/Web but breaks typed SDK; EEX NGP persists nowhere. |
| Is any source live-certified here? | No fresh certification evidence. Static registry defaults are unverified and fail-closed. |
| Is there a customer-usable TSO tariff path? | No. Only development seed data for NTS/BBL/IUK; no path for the other five. |
| Are outages and weather delivered? | No. Both APIs are explicit empty envelopes. |
| Can fixture tests be used as live proof? | No. They use mock transport, synthetic payloads or in-memory DB only. |
| What should root implement next? | P1 SDK parity, P1 one tariff import path, P1 truthful run controls, P1 GIE conformance/certification; then P2 ENTSOG outages and EEX NGP evidence; weather awaits a rights/provider decision. |

No commit, push, source activation, grant, certification, credential read, database access or
permission change was performed by this audit.

## 9. Subsequent reviewed fixes (2026-10-28)

The census above records the pre-fix source inspection; it is retained as the
traceable reason for the fixes. GIE SDK carriers now parse actual API TWh payloads
without inventing coordinates or volume conversions; API-to-SDK fixture tests
pass. ALSI inventory/DTMI require explicit nested `gwh` for energy; scalar/volume
fields remain unknown energy with raw provenance and unit warnings. See
[GIE SDK parity](../architecture/GIE_SDK_PAYLOAD_PARITY.md) and
[ALSI unit contract](GIE_ALSI_MEASUREMENT_UNITS.md). Source/transport/SDK selection:
117pass. Neither change establishes live provider/rights acceptance.

Generic JSON cost refresh now refuses missing/null/nonfinite values and provider
failures; whole-batch validation and rollback prevent partial persistence. EEX
retained decimals are consumed before normalization with explicit provenance;
strategy-series helper adoption remains open. Combined exact-price/parser/cost
selection:147pass. [Cost validation](../architecture/COST_SOURCE_JSON_VALIDATION.md)
and [exact price consumers](../architecture/EXACT_SOURCE_PRICE_CONSUMERS.md)
record boundaries. Unsupported source runners/downloaders and real-business
source adoption remain open; this is not a revised claim that all24 sources work.
