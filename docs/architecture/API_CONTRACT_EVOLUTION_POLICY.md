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

## Non-Goals

- URL versioning (`/v1`, `/v2`): rejected; the unversioned contract evolves
  additively.
- Generated client stubs: SDK DTOs remain hand-written and are guarded by
  parity tests.
