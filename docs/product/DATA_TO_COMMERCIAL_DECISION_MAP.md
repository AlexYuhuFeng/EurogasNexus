# Data-to-commercial-decision map

Owner direction: 2026-10-23. Retain/add/remove data based on supported business
use, not provider count. Target design, with current implementation evidence
explicitly separated. Companion: [European gas business workflows](EUROPEAN_GAS_BUSINESS_WORKFLOWS.md).

## Required value chain

Source → rights and data-quality checks → canonical observation/product →
versioned assumption or calibrated model → business alternative/constraint →
result and uncertainty → decision evidence → operator ownership.

A connector without a consumer, a chart without a question, or a metric without
an economic meaning does not constitute a finished capability. A source failure
must identify affected business work, not only change a global health badge.

| Data family / candidate source | Why a European gas desk needs it | Model use and task placement | What must not be inferred | Priority / present evidence |
| --- | --- | --- | --- | --- |
| Exchange and index data: EEX; licensed ICE/broker sources where authorized | Reference valuation, forward/spot relationships, basis and liquidity context | Typed product catalogue, watchlist/curve/spread views, admissible marks in scenario/backtest inputs | Settlement/index/mid is an executable bid/ask; venue identity is product identity; simulated connector is certified | Core. EEX connector and normalized views exist; product/source binding and quote-only discovery require reconciliation |
| Pipeline physical data: ENTSOG transparency and relevant TSO publications | Identify flow changes, congestion, supply disruptions and route constraints | Compare flow/capacity/outage by point, direction and interval; bind selected facts to route scenario | Published technical capacity is company-booked capacity; observed flow is a contract commitment | Core. ENTSOG connector/persistence exists; exact datasets and scenario consumers must be inventoried |
| Company contracts, capacity/access rights, confirmed commitments and reconciled imports | Determine obligations, scenario availability and actual commercial constraints | Portfolio/obligation book and daily plan; primary input to alternatives | Industry data substitutes for company entitlements; contract daily volume equals remaining stock | Core. Resource records/imported observations exist; not a complete temporal commitment ledger |
| Weather forecasts, observations and climatology: evaluated ECMWF/Copernicus or national/public provider | Assess heating-demand scenarios and forecast revisions; explain demand-related uncertainty | Region-weighted HDD/CDD with declared base/climatology; calibrated demand scenarios with explicit uncertainty and validation | Cold forecast automatically predicts a profitable trade; realized weather was known at decision time | Core decision context, gated analytics. Current Weather connector is a mock shell; weather API/product contract explicitly returns unavailable/empty. No implemented demand forecast claim |
| Storage: GIE AGSI and relevant operator data | Understand regional supply flexibility and seasonal/short-term stress | Storage level/injection/withdrawal context and scenario sensitivity; company rights only from company evidence | Aggregate country inventory is our stock or our withdrawal entitlement | Core context. GIE connector exists; product-level coverage and business-consumer mapping to be checked |
| LNG: GIE ALSI, terminal/operator publications, authorized cargo intelligence | Assess terminal utilization, arrival/send-out context and regas constraints | Cargo/regas workbench with inventory, slot, storage/send-out and delay assumptions | Public terminal capacity implies an available booked slot; vessel location proves contractual cargo availability | Core for LNG business. Readiness and cash/economics primitives exist, not complete operational cargo lifecycle |
| Outage/maintenance and urgent market messages: authorized TSO/terminal/REMIT-compatible sources | Identify time-critical changes to feasible supply and delivery | Deduplicated incident → affected points/resources/routes/cases → reassessment | Unverified message establishes an executed obligation or a causal price forecast | Core if source/licence/coverage confirmed. No new live source claimed by this document |
| FX: ECB reference plus authorized market/forward curves as required | Normalize comparison and model currency cash exposure | Valuation engine, dated cash and explicitly specified FX scenario | Daily reference FX is an executable rate, intraday rate or forward hedge curve | Core. ECB connector and shared explicit FX/cash valuation exist |
| Power load/generation/renewables: ENTSO-E or authorized national sources | Explain gas-for-power demand when relevant to the portfolio/horizon | Optional gas-demand scenario with validated regional linkage | Wind/solar observation alone quantifies gas burn without plant/market model | Conditional. Add only for a named demand use case with calibrated validation and permitted access |
| Carbon/coal/oil and shipping/funding benchmarks | Explain switching, indexed contracts, cargo economics or financing assumptions | Model-specific input groups, never a universal home dashboard | Correlation establishes contract pricing, freight cost or funding availability | Conditional. Each input needs a named pricing/decision model, rights and evidence |
| News and AI summaries | Help operators find and understand evidence | Source-linked investigation and explanation of a selected case | Generated text supplies missing price, contract right, forecast or deterministic valuation | Secondary; may not replace authoritative observations or audit evidence |

## Weather must be a proper data product

Persist issue/run time, valid time, location/region, model/provider/version,
forecast horizon, units, ingestion time, revision and source/licence reference.
Observations and forecasts are different product types. Historical selection uses
only forecast vintages available at the decision time. HDD/CDD also requires base
temperature, aggregation convention, geographic/customer weights and a defined
climatological comparison. A demand model needs training/evaluation periods,
leakage controls, uncertainty and performance against an appropriate baseline.

First useful deliverable can be weather context and explicit scenario sensitivity;
there is no need to claim a predictive demand/price engine before it is validated.
A forecast change should identify affected delivery periods and cases. Users may
accept an assumption into a scenario; the snapshot retains the chosen vintage.

## Physical system and commercial rights remain distinct

Use canonical point/terminal/storage IDs, directions and calendar intervals when
joining physical data. Preserve source measurement type and status. Actual flow,
technical capacity, available capacity and booked company capacity have different
meanings. Route comparison composes the relevant physical evidence with company
rights, tariffs, losses and timing. Missing rights or capacity produces a blocker
or a clearly qualified research scenario, never an implied executable route.

## Source acceptance and removal

Before adding a provider: identify business owner, exact products, access/licence,
coverage, freshness target, units/time semantics, stable IDs, revision handling,
point-in-time retention, quality/refusal behavior, downstream consumer, operational
cost and a meaningful acceptance case. Prefer existing ingestion/data-product
contracts over bespoke direct client calls. Public access does not establish
redistribution rights. No scraping or licence bypass is introduced.

Remove unused or irrelevant sources from the active user workflow only after
checking consumers. Deactivate connectors rather than destroying historical
references. Retain lawful lineage needed to reproduce frozen analyses. Do not
remove a control-plane capability merely because traders should not see it.

## Concrete work sequence

1. Inventory every current source/product against this map and its real consumer.
   Distinguish live adapter, synthetic adapter, empty contract and persisted data.
2. Resolve canonical instrument, physical point and company-resource joins before
   adding dashboards. Show provenance and compatibility at selection time.
3. Compose the daily pipeline/day-ahead/within-day workflow from current verified
   products. Validate missing/stale/denied cases and impact propagation.
4. Implement a rights-reviewed weather product only with exact forecast-vintage
   semantics and a first named scenario consumer; do not activate the mock shell.
5. Extend LNG and optional power/funding inputs only for their corresponding
   business scenarios and independent numerical acceptance.

Success is a defensible business decision with explainable data lineage, not a
larger number of connected sources. Current documents and synthetic acceptance
are engineering evidence, not current provider certification or practitioner UAT.
