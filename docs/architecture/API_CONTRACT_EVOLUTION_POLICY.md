# API Contract Evolution Policy

Chinese companion: [API_CONTRACT_EVOLUTION_POLICY-CN.md](API_CONTRACT_EVOLUTION_POLICY-CN.md)

## Purpose

The public `/api` surface is a shared product contract consumed by five
surfaces: Web, Python SDK, CLI, Windows/Linux desktop shells, and the
bilingual operator documentation. Every consumer is a thin client of the same
contract, so the contract changes only through a deliberate, tested process.

This document is the single policy for evolving that contract. It closes
roadmap problem D (no evolution strategy for the stable unversioned `/api` and
five hand-maintained surfaces).

## Principles

1. **Stable unversioned `/api`.** The public surface keeps the unversioned
   `/api` prefix. Operator-only and development-only routes keep their
   profile-gated `/api/internal` and `/api/dev` prefixes. No `/v1` or
   `/api/v1` aliases are ever served.
2. **Additive-only by default.** New endpoints and new optional response
   fields are the normal evolution path. Existing paths, parameters, and
   field meanings do not change silently.
3. **Breaking changes are a major event.** Removing, renaming, or re-typing a
   path, parameter, or response field requires a written migration plan
   (deprecate → dual-run → remove across at least one release) and an
   reviewed public ExecPlan. Follow `docs/engineering/RFC_PROCESS.md` when the
   change introduces a new normative contract. There is no in-place breaking
   change.
4. **Deprecation is explicit.** A deprecated path or field must carry
   `deprecated=True` in its OpenAPI operation, a `meta.warnings` entry in its
   runtime envelope, and a removal date in this document's deprecation table.
   Deprecated surfaces remain functional until removal.
5. **Backend is the only owner of normalization.** Derived fields (FX
   conversion, tenor, hub, spreads) are computed by the backend; clients must
   consume them instead of re-implementing domain logic.

## Compatibility Gates

These tests fail CI loudly on contract drift:

| Gate | File | What it pins |
|---|---|---|
| Surface stability | `tests/contract/test_api_surface_stability.py` | the exact set of public paths; no `/v1` aliases; declared prefixes only |
| Documented counts | `tests/contract/test_architecture_alignment.py` | alembic head, table count, documented route count |
| SDK parity | `tests/contract/test_sdk_backend_parity.py` | SDK DTOs versus backend payload contracts |
| Realtime contracts | `tests/contract/test_realtime_contracts.py` | SSE/streaming semantics, no Kafka/Redis tokens |
| Validation consistency | `tests/contract/test_validation_consistency.py` | the canonical validation commands in documentation |

## Change Process

1. Record a public ExecPlan using `docs/engineering/EXECPLAN_TEMPLATE.md`,
   listing API impact and rollback; update its index entry.
2. For a new path: add it to `PINNED_PUBLIC_PATHS` in
   `tests/contract/test_api_surface_stability.py`, update the documented
   route count (`RELEASE_READINESS.md` and the
   `test_architecture_alignment.py` assertion) in the same change.
3. For a deprecated path: mark it `deprecated` in the router, add the
   envelope warning, and record it in the deprecation table below.
4. For a refused field: keep it declared in the model, refuse a non-empty value
   with a stable `422` code that names every offending field, record it in the
   refused-field table above, and remove it from every client request builder and
   from the client's request DTO in the same change.
5. Add API, SDK, and contract tests before the implementation is considered
   complete.
6. Run the full validation command set from `CONTRIBUTING.md`.

## Declared Additive Paths

| Path | Declared in | Contract |
|---|---|---|
| `POST /api/optimization/portfolio-network` | Accepted release contract | DB-only `RUNTIME_DECISION`; accepts decision metadata only, never client network/tariff/capacity/price facts |
| `POST /api/optimization/storage-dispatch` | Accepted release contract | assessment-only storage dispatch; RUNTIME_DECISION composes PostgreSQL masters/observations |
| `POST /api/optimization/nomination-window` | Accepted release contract | assessment-only nomination windows; RUNTIME_DECISION loads DB window masters; no submission action |
| `GET /api/optimization/nomination-windows` | Desk clock read (Architecture V2 day view) | READ-floor read of the declared `nomination_window_masters` for one gas day, with the declared clock times and the UTC instants they resolve to on that gas day. It exposes a declaration, not an assessment: no market material, no schedule, no submission. A runtime DB that is not configured answers an empty list with `meta.missing_inputs`, and a configured DB that declares no active master answers a measured zero carrying `NOMINATION_WINDOWS_MISSING`, so "no window closes today" cannot be confused with "the windows were not read" |
| `GET/POST /api/strategies` | CR-03 | versioned strategy research identities; writes are policy-gated and research-only |
| `GET/POST /api/strategies/{strategy_id}/versions` | CR-03 | immutable semantic strategy versions; POST creates a new DRAFT only |
| `PATCH /api/strategies/{strategy_id}/metadata` | CR-05 | update editable strategy metadata; identity/history immutable |
| `PUT /api/strategy-versions/{strategy_version_id}/draft` | CR-05 | replace a DRAFT definition; FROZEN versions are immutable |
| `GET /api/strategy-versions/{strategy_version_id}` | CR-03 | read one immutable version and its `definition_json`/`content_hash` |
| `POST /api/strategy-versions/{strategy_version_id}/freeze` | CR-03 | DRAFT -> FROZEN only; frozen versions are immutable |
| `POST /api/strategy-versions/{strategy_version_id}/fork` | CR-03 | FROZEN -> new DRAFT with `parent_version_id`; never mutates the source |
| `GET/POST /api/strategy-runs` | CR-03 | reproducible run registry; only `EVALUATION` is executable in CR-03 |
| `GET /api/strategy-runs/{run_id}` | CR-03 | read one run with full manifest/provenance |
| `POST /api/strategy-runs` (`run_type=BACKTEST`) | CR-04 | as-of historical evaluation; requires period, frozen version, explicit assumptions |
| `GET /api/strategy-runs/{run_id}/events` | CR-04 | normalized persisted decision events |
| `GET /api/strategy-runs/{run_id}/series` | CR-04 | persisted gross/net cumulative PnL and exposure series |
| `GET /api/strategy-runs/{run_id}/attribution` | CR-04 | persisted market-bucket/cost attribution |
| `GET/POST /api/backtest-experiments` | CR-04 | lightweight SINGLE_RUN experiment grouping |
| `GET /api/backtest-experiments/{experiment_id}` | CR-04 | read one experiment and its run ids |
| `GET/POST /api/shadow-monitors` | CR-06 | scheduled non-executing shadow research monitors |
| `GET/POST /api/shadow-monitors/{id}/pause|resume|retire` | CR-06 | monitor lifecycle changes; history and open alerts preserved |
| `GET /api/shadow-monitors/{id}/evaluations` | CR-06 | immutable evaluation history |
| `GET /api/shadow-evaluations/{id}` | CR-06 | evaluation evidence/result/risk checks |
| `GET /api/shadow-monitors/{id}/drift` | CR-06 | interpretable drift snapshots against explicit baseline |
| `GET /api/shadow-alerts`, `POST /api/shadow-alerts/{id}/acknowledge` | CR-06 | deduplicated alert lifecycle |
| `GET /api/shadow-runtime/status` | CR-06 | scheduler heartbeat/health |
| `POST /api/dev/auth/login` | UX-01 authentication-first entry | development-profile-only credential login mounted with `include_dev`; absent from internal/release; validates operator-configured dev credentials server-side and issues the same backend session as OIDC; never creates or elevates a principal |
| `GET /api/data-products` | Architecture V2 Wave 4 (Unified Data Platform) | READ-floor declaration of the Data Product catalogue: product ids, business names, availability state, time basis, declared source/entitlement families and serving surfaces, plus a per-principal entitlement verdict and a freshness/provenance summary. No API key, secret value, scheduler internal or retry trace is returned; a product the caller is not entitled to is reported `restricted` with no provenance block rather than omitted or shown as zero |
| `GET/POST /api/analysis-snapshots` | Architecture V2 Wave 4 (Unified Data Platform) | `POST` (GOVERNED, ANALYST floor) records an Analysis Snapshot descriptor from the current Active Context; `GET` lists recent descriptors. `GET` keeps the READ floor because a descriptor is lineage/provenance metadata with no commercial values; every value it references stays behind its own commercial endpoint |
| `GET /api/analysis-snapshots/{snapshot_id}` | Architecture V2 Wave 4 (Unified Data Platform) | read one Analysis Snapshot by its reproducibility reference; 404 when the reference is unknown |
| `GET/POST /api/decision-cases` | Architecture V2 Wave 6 (Decision Case) | `POST` (GOVERNED, ANALYST floor) opens a case in the current Active Context; `GET` lists recent cases as compact summaries. A Decision Case is evidence and rationale, never execution approval: no order entry, routing, nomination or settlement semantics exist on this surface |
| `GET /api/decision-cases/{case_id}` | Architecture V2 Wave 6 | read one case with its assumptions, alternatives, evidence, AI findings and decision records |
| `POST /api/decision-cases/{case_id}/evidence` | Architecture V2 Wave 6 | attach one evidence reference (GOVERNED); the first evidence moves the case from DRAFT to OPEN. References are deduplicated and carry the snapshot id that makes the decision reproducible |
| `POST /api/decision-cases/{case_id}/decisions` | Architecture V2 Wave 6 | reviewer-gated (REVIEW) recording of the human decision. The actor is the authenticated identity, never a body field. A case without evidence is refused with 409 `case_not_decidable` and its blocker codes |
| `POST /api/decision-cases/{case_id}/reopen` | Architecture V2 Wave 6 | reviewer-gated (REVIEW) reopen; every record is preserved, nothing is deleted |
| `GET /api/projections/market-context` | Architecture V2 Wave 5 (application projections) | READ-floor coherent read model over market observations, normalized quotes, intraday opportunities, spreads and monitoring alerts on one explicit time basis and as-of instant, with a per-slice freshness summary. Commercial-boundary paths: a platform-administration identity without a commercial role is refused |
| `GET /api/projections/portfolio-snapshot` | Architecture V2 Wave 5 | READ-floor coherent portfolio read model (summary, screen orders, PnL snapshots, resource context) with per-slice freshness |
| `GET /api/projections/review-context` | Architecture V2 Wave 5 | READ-floor coherent review read model (evidence, decisions, warnings) for the review workflow |
| `GET /api/projections/scenario-context` | Architecture V2 Wave 5 | GOVERNED-floor (ANALYST) scenario and route-economics read model. The projection keeps the floor of the endpoint it composes, so it cannot widen access; it exists to remove client-side joins, not to relax authorisation |
| `GET /api/jobs` | Architecture V2 Wave 8 (unified jobs) | READ-floor list of tracked long-running operations (ingestion, dataset build, optimisation, backtest, report, agent run, snapshot) newest first, filterable by status, kind and principal. Job telemetry only: no secret, no stack trace, no licensed payload |
| `GET /api/jobs/{job_id}` | Architecture V2 Wave 8 | read one job with its progress, output references, correlation id and, on failure, the stable error code from the product taxonomy; 404 when the job is not tracked |
| `POST /api/jobs/{job_id}/cancel` | Architecture V2 Wave 8 | GOVERNED-floor (ANALYST) cancellation of a cancellable, non-terminal job. A finished job answers 409 `job_already_finished` and a protected one 409 `job_not_cancellable`, so the surface never claims to have stopped work it did not stop |
| `POST /api/research/cash-valuation` | Shared cash valuation capability (2026-09-30) | Sandbox-only (GOVERNED, ANALYST floor inside the commercial boundary) adaptation of the one shared cash-flow engine: caller-supplied canonical `concept:value` references (never resolved or entitled — `meta.references_verified: false`), exact decimal strings for every amount/FX rate/discount factor (JSON numbers refused), ISO dates, and Decimals serialized as exact strings. Refusals are typed (`422 cash_valuation_input_invalid` for wire-syntax violations, `422 cash_valuation_refused` with the engine's stable codes). No persistence, provider, audit record, trade, nomination or settlement; `meta.customer_approval` is always `false`. See [CASH_VALUATION_CAPABILITY.md](CASH_VALUATION_CAPABILITY.md) |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` | Contract revision integration (2026-10-01) | GOVERNED-floor (ANALYST) bounded history of one contract's captured immutable economic revisions, inside the commercial boundary, oldest revision number first (`limit` ≤ 200 with `offset`). Every returned row is verified (reviewed capture origin, stored hash, canonical decode, contract id and schema version) before it is served; an unknown contract is 404 `upstream_contract_not_found` while an existing contract with nothing captured is an empty page with `revision_count` 0 and an explicit warning. Reading captures nothing and re-attributes nothing. Honest evidence only: a capture is not a complete history, and the stored economics carry `payment_terms: null` — no payment date, discount factor or valuation is derived or implied |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions/{contract_revision_id}` | Contract revision integration (2026-10-01) | GOVERNED-floor (ANALYST) read of one verified captured revision, explicitly scoped to `contract_id`: a revision id from another contract answers the same 404 `contract_revision_not_found` as an unknown id. An integrity-verification failure is a structured 409 carrying the repository's stable code and a fixed message only (no stored row content, driver text or SQL). The payload preserves capture origin, schema version, content hash, capture instant, original recorder and raw operator notes |
| `GET /api/market/products` | Trader desk conventions (2026-10-30) | READ-floor pure calendar resolution of European gas product codes (`WD`, `DA`, `WE`, `BOM`, `M+n`, `Q+n`, `S+n`, `GY+n`, `Cal+n` and absolute `Nov-26`, `Q1-27`, `Sum-27`, `Win-27`, `GY-27`, `Cal-27`) against `trade_date` (default today UTC) into first/last gas day, UTC delivery interval and DST-true delivery hours on the `EU-CAM-UTC-2025` calendar. Without `code` it returns the standard desk strip. Unknown or fully delivered codes answer 422 `unknown_product_code`. No DB read; exchange holidays are not applied |
| `GET /api/market/price-conversion` | Trader desk conventions (2026-10-30) | READ-floor conversion of one price between EUR/MWh, GBP/MWh, USD/MWh, GBp/th, USD/MMBtu, EUR/GJ and EUR/kWh on International Table BTU factors. FX comes from a named benchmark fix: `fx_source` `ECB` (default, public), `WMR` (WM/Reuters 4pm London, LSEG) or `BFIX` (Bloomberg), optional `fx_fixing` id, on `fx_date` or as the per-pair arithmetic mean over `fx_average_from`..`fx_average_to` (LNG pricing-period practice), latest fix otherwise; USD-quoted pairs are crossed to EUR base. Licensed WMR/BFIX rows are operator-imported only (`scripts/ops/import_fx_fixings.py`) and row-entitlement filtered, so an unentitled principal gets no licensed rate. Explicit `gbp_per_eur`/`usd_per_eur` override per currency. The fix, value dates and count used are echoed; a missing rate yields `null` per target (or 422 `fx_rate_unavailable` for an explicit `to_unit`); unknown source/fixing is 422 `unknown_fx_fixing`. No rate is ever assumed. `GET /api/market/fx` is now row-entitlement filtered for the same reason |
| `GET /api/market/interest-rates` | Contract financing benchmarks (2026-10-30) | READ-floor, entitlement-filtered overnight benchmark fixings (SONIA from the Bank of England, €STR from the ECB, SOFR from the NY Fed) newest first per benchmark (`benchmark`, `limit` ≤ 400), plus the benchmark catalogue (currency, day count, administrator, required attribution). Rows come only from `scripts/ops/ingest_interest_rates.py`; nothing is interpolated. 422 `unknown_benchmark` |
| `GET /api/market/financing-rate` | Contract financing benchmarks (2026-10-30) | READ-floor resolution of a contract financing rate = benchmark fixing with the latest value date on or before `as_of` + `spread_bps`, returned on the benchmark's own day count and restated on ACT/365F (the basis the early-cash term accrues on), with fixing date, staleness and source. A fixing older than `max_staleness_days` (default 7) is refused with 422 `financing_rate_unavailable` instead of using a stale rate |
| `GET /api/storage/target-trajectory` | Trader desk conventions (2026-10-30) | READ-floor, entitlement-filtered filling trajectory of one AGSI code (default `EU`) against a configurable storage target (`target_pct` default 90, `deviation_pp` default 0, window 1 Oct – 1 Dec): fill, gap, required net injection per day to window opening and deadline, recent net-injection pace and projected deadline fill with status `target_met`/`on_track`/`behind`/`unreachable`/`withdrawal_season`. No rows for the code answer 200 with `data: null` and a `storage_series_unavailable` warning (a data state, like other reads); rows that cannot support a trajectory answer 422 `storage_series_unavailable`. Backward-looking pace only; not a forecast or regulatory advice |
| `GET /api/weather/forecasts` | Declared additive ECMWF research read (2026-10-28) | Authenticated, entitlement-filtered point-in-time ECMWF grid forecast readings. The caller supplies non-empty `series_ids`, `entity_ids`, `prediction_origin`, `valid_from` and `valid_to` as aware ISO datetimes, plus optional `limit` (1–256, default 100); `valid_to` must follow `valid_from`. Every row exposes `issued_at_utc`, `valid_at_utc`, `available_at_utc`, degC temperature, requested/grid coordinates and GRIB/record SHA-256 values; the API performs no interval aggregation or station inference. Requires a live ECMWF provider certification and ECMWF source entitlement: a missing, expired or uncertified record answers 503 `forecast_source_unavailable`; storage failures answer 503 without inventing values. `meta.research_only` is true and `HUMAN_REVIEW_REQUIRED` is warned |
| `POST /api/weather/degree-days` | Declared additive ECMWF research calculation (2026-10-28) | Authenticated, entitlement-filtered degree-day calculation from persisted ECMWF forecasts. The caller must declare 1–64 unique point bindings (`point_id`, `series_id`, `entity_id`, `location_id`, `region`, exact decimal `weight`), each weight in `[0, 1]` with the set summing exactly to `1`; 1–7 unique gas days; an aware `prediction_origin`; heating and cooling bases; an approved `gas_day_calendar`; `max_hold_minutes` (1–10080); and `min_covered_fraction` (`0`–`1`). The bridge uses `LEFT_HOLD_INSTANT` with the declared hold as its maximum gap, reports the selected forecast vintage, feature-policy hash and coverage diagnostics, and reports nullable daily values with `MISSING_COVERAGE_NULL` rather than zero-filling; `NOT_READY` means no bridge intervals were available. Same certification and entitlement gates; no persistence, forecast invention, trade, nomination or settlement |

## Additive Field Declarations

Field-level additions to existing paths. They introduce no new path, relax no
floor and change no status code; a caller that does not send the optional field
keeps its previous behaviour.

| Path | Field | Contract |
|---|---|---|
| `POST /api/route-cost/recommend` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4: the reproducibility reference a produced recommendation cites. Verified against persisted Analysis Snapshots before the run — `422 analysis_snapshot_not_found` when the reference is unknown, `503 runtime_db_not_configured` when no runtime database can verify it |
| `POST /api/route-cost/resource-pool/optimize` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to this run path in the Wave 5 follow-up: same verification and the same refusal codes as the recommendation path. The field is absent from `data` when the caller cites no snapshot, so such a caller's payload is unchanged |
| `POST /api/strategy-runs` (`run_type=BACKTEST`) | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to the strategy backtest run: verified against persisted Analysis Snapshots before the run (no run row and no job are created when it is refused), echoed on the response, and absent when the caller cites nothing |
| `POST /api/analysis/query` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to the analysis (AI evidence) path: verified before the input snapshot is loaded and before any provider call, so an unverifiable citation can never be paid for with an external request. Same refusal codes as the other paths; the field is absent from `data` when the caller cites nothing, and the citation is part of the persisted analysis record |
| `POST /api/reports/portfolio` | `analysis_snapshot_id` (request, optional; echoed on `data`) | Architecture V2 Wave 4 scope extended to the portfolio report: verified before the run, echoed on the report, and recorded on the tracked `REPORT` job as the snapshot the report was computed against (an empty reference when the caller cited nothing). The stored report record keeps its sections and source references; it has no column for a cited reference, which is recorded here rather than implied |
| `GET /api/optimization/nomination-windows` | `next_gas_day`, `next_opens_at_utc`, `next_closes_at_utc` (per window row, optional in the sense that a client may ignore them) | The day view follow-up, and the same family's own field: window masters are daily rules, so once the requested gas day's window has closed the actionable instant is the *following* day's occurrence of the same clock. Both occurrences are resolved on the gas-day calendar by the route rather than by a client adding a day to a clock, and a JSON client that ignores the three fields sees exactly the previous payload |
| `GET /api/decision-cases/{case_id}` | `pack` (object, additive) | The decision pack: the same case composed for the human who signs it — context, evidence with each cited snapshot's resolvability **measured** (`true`/`false`/`null`, the last meaning the reference cites none), assumptions, alternatives, AI findings, warnings, the recorded decision, the case's audit trail (its acts are recorded under `decision_case:<case_id>`), the pack's own blockers beside the case's, `signable`, the platform's statement that it holds no signature, and a canonical `content_hash` with its basis. It rides on this read rather than a new path because it *is* this resource, not a second answer about it; a client that ignores it sees exactly the previous payload. Reading a case already needs the runtime database, so nothing new is refused |
| `GET /api/route-cost/upstream-contracts` | `edit_token` (per contract row, additive) | The bounded stale-edit precondition (2026-10-02): an opaque token over the whole persisted contract row — identity, economics, display metadata, raw operator notes and the updated instant — not the captured revision number and not a signature. A client that ignores it sees exactly the previous payload; a client that edits a row sends it back as `expected_edit_token`. The other consumers of the same repository read (projections, resource-pool composition, agent context) are left at their previous shape |
| `POST /api/route-cost/upstream-contracts` | `expected_edit_token` (request, optional) and `edit_token` (response) | The same precondition. Omitted or null means create-only; a supplied token that no longer matches the locked row, or that names no stored row, is refused `409 contract_edit_conflict`; a token that is not this API's `sha256:` token shape is refused `409 contract_edit_token_malformed`. Both refusals are sanitized, change nothing, and the response keeps every existing field plus `edit_token`/`write_outcome`/`latest_revision` |
| `POST /api/route-cost/upstream-contracts` | `payment_terms` (request, optional) | S2b declared payment terms: a strict canonical `contract-payment-terms/v1` document (validated by the shared domain decoder, not Pydantic, and stored as its own canonical JSON) or an explicit `null`. **Omitted preserves** the stored declaration — presence is read from `model_fields_set`, so a client that does not know the field (every existing client) never erases it; explicit `null` clears it. The nested contents are never echoed: a refused declaration answers `422` with the decoder's own stable, sanitized code in `detail.error` and reason, and nothing is written. A declared change is captured as an explicit v2 revision |
| `GET /api/route-cost/upstream-contracts` | `payment_terms` (per contract row, additive) | The additive public read of the same declaration: the strictly decoded canonical document, or `null` for "not stated". A stored declaration that fails canonical verification refuses the read with `409 contract_payment_terms_corrupt` and a fixed message rather than serving corruption as absent. No date is resolved and no valuation runs |
| `GET /api/route-cost/upstream-contracts/{contract_id}/revisions` and `.../revisions/{contract_revision_id}` | `snapshot.payment_terms` (additive; `schema_version` may be `upstream-contract-revision/v2`) | The captured declaration is served read-only from the verified immutable revision for revisions captured while terms were declared; v1 revisions keep `payment_terms: null` and their pinned bytes/hash. The evidence warnings state that a capture neither asserts when terms applied nor resolves a payment date |

## Refused Request Fields

A declared field the pipeline never reads is a claim the platform cannot honour: a caller that fills
it in receives an unmodified result while believing their selection was applied. Such a field is
**refused with a stable error code instead of ignored**, is listed here, and stays declared (removing
it would turn an explicit refusal into a silent drop for a caller that still sends it). The refusal is
raised before the run is loaded, tracked or paid for, and an empty value is never an offence. Every
refusal code below is catalogued in the product error taxonomy, so a client classifies it (family,
severity, recoverability) rather than reading a raw status code.

| Path | Field | Contract |
|---|---|---|
| `POST /api/analysis/query` | `selected_terms`, `selected_assets`, `selected_contracts`, `include_sections` | `422 analysis_selection_not_supported`, naming every non-empty field in `detail.fields`. The deterministic builders read the snapshot, the task and the question, so a term, asset, contract or section selection describes work that does not happen. Evidence references belong in `question`, which is the prompt the platform records and the provider receives |
| `POST /api/reports/portfolio` | `portfolio_id`, `selected_resources`, `selected_contracts`, `selected_strategies` | same code and the same `detail.fields` contract: a report is computed from the whole entitled snapshot, so a portfolio/resource/contract/strategy selection would be a scope the caller believed was applied |
| `POST /api/agent/research` | `strategy_ir` | `422 strategy_ir_not_accepted`: the orchestrator never read it, so a caller could believe its own specification had been run while the pipeline validated a candidate of its own. The strategy registry is the path that owns a specification |
| `POST /api/agent/research` | `profile` (validated, not refused) | `422 agent_profile_unknown` when the profile is not one the platform declares; a declared profile that never reached all of its stages is reported with `PROFILE_STAGES_NOT_REACHED:<stage,…>` rather than refused, because stopping short is often the honest outcome |

## Deprecation Table

| Surface | Deprecated since | Removal planned | Status |
|---|---|---|---|
| `/api/workflows/*` (10 legacy shells) | 0.5.x (S4.3) | after Web/SDK/CLI migrate to the domain-specific `/api` endpoints | removed in 0.5.x after Web/SDK/CLI migration; legacy paths now return 404 |
| `actor` (request field) on `POST /api/review/decisions` | 0.5.x (W0-03 C13) | when no caller still sends it | accepted but never used: the platform records the authenticated identity as the actor of the decision and of its audit events. A value that disagrees with the identity is reported as an `ACTOR_CLAIM_IGNORED:<claim>` envelope warning, so a caller learns its claim was not recorded. The field became optional in the same change, so omitting it is the supported form |
| `authentication` value `not_installed` on `GET /api/health` / `/api/health/live` | 2026-09-19 (owner decision D1) | when no consumer switches on it | **Replaced, not removed**: every route profile installs authentication now, so no shipped profile produces the value. It stays declared in the response type for a profile that installs nothing, and the payload reports `enforced` by default or `anonymous_allowed` when the deployment itself opted into trusting its network (`EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS`). A consumer that only handled `enforced`/`not_installed` treats `anonymous_allowed` as the old value, which is exactly what it is |

## Deliberate Narrowings

Behaviour changes that refuse more than they used to, recorded here because they are visible to a
caller rather than additive.

| Surface | Change | Why |
|---|---|---|
| Every `/api` path except the credential-exempt ones | **A caller that presents no credential is refused.** Before D1 the `development` and `internal` profiles installed no authentication and served such a caller as the compatibility principal (data scopes `("*",)`, role `OPERATOR`). They now answer 401 `public_api_token_missing` when a deployment token is configured, or 503 `public_api_token_not_configured` when none is, and the identity dependency adds its own 401 `authentication_required` refusal as a backstop. The exempt paths are `/api/auth/*`, `/api/dev/auth/*`, `/api/health` (so `live` and `ready`), `/api/dev/health` and `/api/internal/health` | Owner decision D1: identification is the default and trusting the network is a deployment's own, reported statement. The SDK, CLI, MCP and Web clients are unaffected - they already present the deployment token or a session |
| `/api/internal/*` (12 paths) | **Declared permissions where there were none.** The route-permission gate was not installed in the `internal` profile, so these paths never resolved a permission; installing the gate exposed that a mounted path with no registry entry answers 500 `permission_not_declared` | The registry is enforcement, not documentation. Each entry mirrors the floor the route already enforced in its handler (`validate_internal_operator_headers`), so nothing that could reach them before is refused now |
| `POST /api/route-cost/upstream-contracts` | **A write with no stored-contract edit token is create-only.** Before this change a POST whose `contract_id` already existed overwrote that row (captured and audited, but silently last-writer-wins). An existing identity is now refused `409 contract_edit_conflict` unless the request carries the current token from `GET /api/route-cost/upstream-contracts`; a token-bearing request for a nonexistent identity writes nothing; a concurrent create loser is refused the same way instead of taking over the winner. Permission, acting principal, capture/audit transaction and the error envelope are unchanged; the plain repository upsert stays an internal compatibility path, not an API write path | The route is a multi-writer operator surface over one mutable row; without a read precondition a draft loaded before another operator's save silently replaced their terms, and the captured revision could only prove afterwards what had been replaced. The token is an integrity/identity check on the row (not cryptographic authenticity and not a monotonic lifecycle counter), and there is no overwrite bypass. See [CONTRACT_PAYMENT_INTEGRATION_PLAN.md](../engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md) section 13 |
| `POST /api/route-cost/upstream-contracts` and `GET /api/route-cost/upstream-contracts` | **The edit token schema is `upstream-contract-edit-token/v2`.** S2b added the declared payment-terms carrier column to the covered field set, so a token loaded before the upgrade can never compare equal after it: a client holding an open draft receives `409 contract_edit_conflict` and must reload the contract before saving. There is deliberately no v1 comparison fallback | The token covers the whole persisted row, and the carrier holds operator declarations that a stale draft could otherwise erase. Storing the terms on the row without covering them in the precondition would let a draft loaded before a terms-only edit overwrite it silently. **Deployment:** no client code change is required to keep reading, but any open editor session must be reloaded after the rollout |
| `POST /api/route-cost/resource-pool/optimize` | **The request must carry an explicit finite `annual_financing_rate_pct`.** The field has no server-side default any more: omitting it, or sending `null`, a boolean, a string (including a blank string), `NaN` or ±infinity, is refused `422` by request validation instead of being filled with the previous implicit `6.0`. An explicitly supplied `0` is accepted and is a recorded zero (a zero early-cash term). No other field, sign convention or arithmetic rule changed | The optimiser credits `base_cost × rate / 100 × max(upstream_lag − screen_lag, 0) / 365` to unit margin, so a server-filled rate priced a margin from an assumption the caller never declared. The Web client already refused an unknown rate and sent the resolved value, so it is unaffected; direct API/SDK callers must now declare the rate they want. Boundary change recorded in the business acceptance reconciliation note of 2026-10-06; it establishes no dated cash-need profile, day-count convention, discount factor or NPV |
| `POST /api/route-cost/resource-pool/optimize` | **Payment/sale lags are explicit declarations.** `PortfolioResource.upstream_payment_lag_days` is required (the previous server-side default `20` is removed) and `PortfolioSaleOption.screen_sale_cash_lag_days` must be declared as whole non-negative days or an explicit `null` (the previous `1` default is removed). Supplied values must be strict integers: booleans (which Python counts as integers), floats, strings and negatives are refused `422`, and an explicit `0` is a recorded zero. The optional per-resource `screen_sale_cash_lag_days` override keeps the same whole-day rule. When a pair's effective lag is unknown (no override and an explicit `null` option declaration) the pair is refused and reported (`SALE_CASH_LAG_MISSING` / `SALE_CASH_LAG_UNKNOWN`) instead of being credited as if paid on the delivery day. The composed `GET /api/route-cost/resource-pool/options` read stops substituting the removed one-day default: an undeclared eligible-contract lag is composed as `null`. No other field or arithmetic rule changed | The lags feed the same early-cash term as the rate (`base_cost × rate / 100 × max(upstream_lag − screen_lag, 0) / 365`), so server-filled values priced margin from lag terms the caller never declared, and assuming a zero-day sale lag would produce the largest possible credit. Recorded in the business acceptance reconciliation note of 2026-10-06; no dated cash schedule, day-count convention, discount factor or NPV is introduced |

## Non-Goals

- URL versioning (`/v1`, `/v2`): rejected; the unversioned contract evolves
  additively.
- Generated client stubs: SDK DTOs remain hand-written and are guarded by
  parity tests.


## Strategy ownership and sharing — 2026-10-22

The public path registry now contains 187 paths (previously 182). Added:

- `/api/me/groups` (GET): the authenticated user's active sharing groups.
- `/api/access/groups` (GET/POST): ADMIN group catalogue and creation.
- `/api/access/groups/{group_id}` (PATCH): ADMIN group status/name changes.
- `/api/access/groups/{group_id}/members/{principal_id}` (PUT/DELETE): ADMIN membership changes.
- `/api/strategies/{strategy_id}/sharing` (PATCH): owner-selected PRIVATE, PUBLIC or GROUPS audience.

Strategy responses add `owner_principal_id`, `visibility`, `shared_group_ids` and
`can_manage`. New strategies are PRIVATE and bind ownership to the authenticated
active directory principal, never a request's attribution text. PUBLIC grants
read access within this deployment, still subject to roles and source licences;
it grants no edit or cross-region transfer permission. GROUPS requires explicit
active groups the owner belongs to. Shared readers cannot mutate strategy state.

This deliberately narrows existing access: hidden strategies and their child
resources return 404; lists filter before limiting. Jobs are restricted to their
server-recorded owner; a foreign `principal` query returns an empty list. Review
and portfolio projections withhold inaccessible strategy-linked records. Existing
ownerless strategies remain PRIVATE and quarantined pending verified ownership
assignment; migration 0040 does not infer owners from free-text attribution and
refuses downgrade to code that would expose these records.

Empty identity-key scopes now mean public-baseline access, not inheritance of
commercial grants. Explicit key scopes are intersected with current principal
grants. Operators must replace old implicit-scope keys with approved explicit
scopes; see [API keys](../operations/API_KEYS.md).

Job ownership follow-up: migration 0041 adds nullable `owner_principal_id` to job
records. HTTP producers bind this from the active named identity; display
`principal` remains attribution and an optional narrowing filter. Name-only legacy
jobs have no read/cancel grant until independently verified ownership is assigned.
A principal-name/ID collision cannot grant access.

## 2026-10-27 additive capacity billing contract

`POST /api/research/capacity-billing` adds a sandbox-only, authenticated research
calculation with strict decimal-string amounts and explicit aware billing times.
The shared domain engine owns arithmetic; typed SDK and Web consumers must not
recompute it. It establishes neither booked rights nor physical readiness.
Existing routes and authorization remain unchanged. See
[capacity billing capability](CAPACITY_BILLING_CAPABILITY.md) and
[delivery reconstruction plan](../engineering/DELIVERY_RECOVERY_EXECPLAN.md).
Public census: 196 paths / 210 operations.

`POST /api/research/lng-economics-only` is likewise additive and sandbox-only.
It requires explicit ordered energy stages, charged cost bases and dated cash
inputs. Readiness remains NOT_ASSESSED; API and SDK delegate to the shared domain
composition. See [LNG capability](LNG_ECONOMICS_ONLY_CAPABILITY.md).

## 2026-10-28 additive route-date and provenance carriers

Route recommendation accepts an explicit `tariff_applicability_date` and optional
candidate date/source references; results preserve date and source provenance.
Caller references are labelled unverified and confer no access. Resource-pool
runtime composition accepts `gas_day`; sandbox composition refuses that field.
PortfolioSnapshot uses its existing normalized trading-context gas day for tariff
selection. Unknown cost is never substituted with zero; missing price/cost basis
or conflicting dates blocks allocation. Existing paths/counts remain unchanged.
See [consumer contract](ROUTE_TARIFF_DATE_CONSUMERS.md).

## 2026-10-28 additive ECMWF forecast and degree-day paths

The stable public surface now includes `GET /api/weather/forecasts` and
`POST /api/weather/degree-days`. They are additive research paths: the legacy
shells `GET /api/weather/stations`, `GET /api/weather/observations` and
`GET /api/weather/hdd-cdd` remain mounted with their existing empty-envelope
behaviour, and no existing path, parameter or response meaning changes. This
declaration records a contract; it is not an acceptance, production-readiness or
operational-forecast claim.

**Point-in-time inputs.** `GET /api/weather/forecasts` selects readings by the
caller's explicit `prediction_origin`, `valid_from` and `valid_to`, and each
returned row preserves `issued_at_utc`, `valid_at_utc` and `available_at_utc`;
the API performs no interval aggregation. `POST /api/weather/degree-days`
requires explicit `prediction_origin`, `gas_days` and `max_hold_minutes`; it
reports `selected_forecast_vintage`, `feature_policy_hash`, the resolved gas
days and the query limit, and reads persisted forecasts across the declared
window extended by the hold. Neither path defaults a missing origin, window or
vintage.

**Weights.** Degree-day weights are caller declarations, not server inferences.
Each binding names one persisted `point_id`/`series_id`/`entity_id`/`location_id`
and one `region`; point and location ids must be unique; all bindings must share
the request region (which may be supplied once); each weight is an exact decimal
in `[0, 1]` and the bindings must sum exactly to `1`. The response warns
`CALLER_DEFINED_REGION_WEIGHTS`.

**Coverage.** `min_covered_fraction` is an explicit request field, not a default.
The computation uses the declared `LEFT_HOLD_INSTANT` temporal method with
`max_hold_minutes` as its maximum gap, caps the query at 256 forecast rows and
the bindings at 64 points. Insufficient daily coverage produces null daily
metrics with an explicit missing reason. When no bridge intervals are available,
it returns `NOT_READY` with diagnostics and `FORECAST_INPUT_NOT_READY`. The
`MISSING_COVERAGE_NULL` warning declares the missing-value policy. Missing coverage is never replaced by zero, and a
calibration or station value is never substituted for an absent grid point.

**Research restrictions.** Both paths return `meta.research_only: true` and the
`RESEARCH_ONLY`/`HUMAN_REVIEW_REQUIRED` warnings; the degree-day envelope also
sets `meta.human_review_required: true`. Both carry ECMWF Open Data attribution
(CC BY 4.0). They perform reads and a calculation only: no persistence, no
forecast invention, no provider call at request time, and no trade, order,
nomination or settlement semantics. Existing legacy weather endpoints are not
deprecated by this addition.

**Authentication and source certification.** Both paths sit behind the
deployment's public API authentication, named identity, declared route-permission
and commercial-access gates. They additionally require derived-data access to
`ECMWF_OPEN_DATA` (`weather_forecasts` / `weather_degree_days`), and returned
rows are filtered by entity/source entitlement. Before reading, each path checks
the latest `ProviderCertificationRecord` for `ECMWF_OPEN_DATA`; no record, an
expired record, or a gate that does not allow live use answers
`503 forecast_source_unavailable`. A storage failure or malformed stored data
answers `503` with a sanitized code rather than an empty or invented value.
Bridge or domain violations of the declared bindings, weights, calendar or
coverage policy are refused as `422 invalid_degree_day_inputs`; request-schema
violations use the platform's standard `422` validation response. Neither form
computes a value.


## 2026-10-29 native physical-rate representation (RFC0005)

`GET /api/physical/flows` and `GET /api/physical/capacity` add an explicit
`quantity_basis=native` representation. Default `quantity_basis=volume` keeps the
existing numeric, non-null volume DTOs and returns all admitted rows; the new
`limit` applies only to native mode. Legacy ENTSOG volumes from unverified
normalization are withheld with a warning rather than rewritten, zero-filled or
offered as physical truth. A valid native energy rate has no volume and is served
only in native mode. An empty volume result does not mean zero physical flow.
Other sources retain their finite volume contract.

Native mode accepts `limit`1..2000 (default200) and an optional exact `point_id`
(up to128characters). A query exceeding the native bound answers400
`native_query_overflow`, without silently truncating the result. Authentication,
route permission, commercial access and source entitlement remain authoritative;
row filtering precedes projection and metadata. Invalid stored native content
answers503 `native_rate_invalid` with a fixed message, not raw values or SQL.
The source-format/normalizer namespace is separate from provider revision history.

Native rows carry the existing point/source/period identities plus
`quantity_basis`, `normalizer_version`, `operator_key` (nullable),
`native_rate_json`, `raw_archive_id`, `payload_sha256` and `received_at_utc`.
`flow_status` and `period_type` preserve captured provider labels when available;
they do not infer finality or physical authority. The
native payload preserves original `value_text`/`unit_text`, exact decimal strings
for native and canonical rates, declared dimension and hourly/daily rate basis.
Energy exposes `energy_kwh_per_day` and null volume; volume exposes
`volume_mcm_per_day` and null energy. The backend revalidates the payload from its
source strings. No assumed calorific conversion exists. Timestamps remain
explicit instants; missing provenance is not replaced with a clock default.

The same two paths accept optional `from_utc`/`to_utc` aware ISO-8601 query
instants for a native period window. Both must be supplied or neither; naive
instants are refused, each is normalized to UTC, and `to_utc` must be later than
`from_utc`. A window is accepted only with `quantity_basis=native`; in volume mode
it answers 422 `native_window_invalid` with a fixed message that echoes no input.
The window is a half-open period **overlap**, not containment: a row is selected
when `period_start_utc < to_utc` and `period_end_utc > from_utc`. A longer
technical-capacity observation that covers a requested daily-flow window therefore
remains visible instead of being dropped. The overlap predicates run before native
ordering and the `limit + 1` probe, so overflow still answers 400
`native_query_overflow` and a narrower window can make the same native query fit.
Clients comparing flows with capacity should send the same explicit query window to
both paths. The window selects captured observations only; it is not a complete
history or a provider revision ledger, makes no calorific-value (CV) conversion,
and defaults no clock time when either instant is omitted.

The SDK adds separate typed native methods in `native_physical`; existing
`physical` methods remain volume-only. Clients must not pair different operators,
points, directions, dimensions or incompatible periods, nor interpret absent
quantities as zero. Native rows do not prove booked capacity or execution rights.
See [RFC0005](../engineering/RFC-0005-ENTSOG-NATIVE-RATES.md). No path or operation
was added: the exact census stays191paths/205operations.

## 2026-10-30 additive spread lab contract

`GET /api/research/spread-series` lists the daily close series the caller is entitled
to (hub, tenor, source, unit, first/last date, day count). `POST
/api/research/spread-analysis` builds a weighted spread of one to four of those series,
reports its statistics (z-score, percentile, AR(1) half-life) and backtests one
declarative rule (z-score mean reversion or fixed bands) with positions decided at
close t and P&L earned from t to t+1. Both sit under the existing `/api/research/`
GOVERNED prefix and filter rows by data entitlement; neither creates an order. A
mixed-unit spread, an unknown series or an invalid rule is a 422
`spread_analysis_invalid`. Public census: 198 paths / 212 operations.
