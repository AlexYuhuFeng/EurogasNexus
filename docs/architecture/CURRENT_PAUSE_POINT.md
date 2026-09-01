# Current Pause Point

Chinese companion: [CURRENT_PAUSE_POINT-CN.md](CURRENT_PAUSE_POINT-CN.md)

## Status

Date checked: 2026-07-22

Eurogas Nexus is a `0.5.0` preview-release worktree containing the FastAPI
backend, PostgreSQL runtime schema, Python SDK, CLI, React/Vite Web workspace,
Tauri Windows/Linux desktop clients, and role-based deployment tooling.

It is a European natural-gas market-intelligence, optimization, and
decision-support product. It is not an execution venue, order router,
nomination-submission system, settlement platform, legal-advice tool, or ETRM.

## Verified Runtime Baseline

The most recently validated local PostgreSQL test runtime has:

```text
alembic_revision: 0023_storage_nomination_masters
required_tables: 45
missing_tables: 0
source: runtime-postgresql
```

Repository schema head and the explicit local test migration are both
`0023_storage_nomination_masters`, with 45 required tables. No
production database was contacted.

Current import evidence:

```text
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
app import ok
92
```

> `len(app.openapi()['paths'])` is the version-stable endpoint count. The raw
> `len(app.routes)` is FastAPI-version-dependent (25 with FastAPI 0.141.x's lazy
> router inclusion) and should not be used as a stable health metric.

Clients obtain runtime data through `/api` or the SDK. They do not connect to
PostgreSQL, read backend files, or call market/infrastructure providers.
Provider credentials are backend-owned and are never returned in plaintext.

## Current Product Shape

- Public API: stable unversioned `/api`.
- Operator API: `/api/internal`, protected by the backend internal token and
  principal header where implemented.
- Development API: `/api/dev`, profile-gated.
- Runtime truth: PostgreSQL with Alembic-managed schema.
- Web: shared map-first trader workspace.
- Desktop: Tauri shells for Windows x64 and Linux x64/ARM64.
- Deployment: distinct Server, Client-only, and AllInOne assets. The Windows
  AllInOne NSIS package provisions the loopback-only Docker/PostgreSQL/API
  runtime and desktop Client on a Docker-ready evaluation workstation. Server
  deployment remains private-network/VPN preview-only until external security
  acceptance. `EUROGAS_NEXUS_DEPLOYMENT_POSTURE` defaults to
  `private_network_preview`; `security_accepted` is effective only with an
  existing `EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE` file.
- Preview market data: source-shaped simulated providers write to PostgreSQL
  and follow the same backend/API/client path as licensed feeds.
- Intraday decisions: normalized L1 quotes trigger backend route-adjusted
  scans; persisted opportunities are exposed through API/SDK and polled by the
  Network, Market, and Strategy workspaces every 10 seconds. Expired snapshots
  are never left actionable.
- Monitoring and DeepSeek: a PostgreSQL-backed worker normalizes opportunity,
  strategy, and source-failure alerts every 10 seconds. Stable fingerprints
  prevent repeated provider charges for an unchanged event. The top-bar Alert
  Center supports acknowledgement and explicit live DeepSeek dialogue. A real
  provider connection, three alert enrichments, and one interactive response
  were validated on 2026-07-22; automated tests remain offline.
- Strategy shadow-run persistence: every `POST /api/strategy-lab/evaluate`
  result is written to `strategy_runs` and `strategy_allocation_targets`, with
  a `run_id`, indicative `paper_pnl_gbp`, cumulative PnL, and hit flag. Read-only
  `GET /api/strategy-lab/runs`, `/runs/{run_id}`, and `/summary` aggregate
  cumulative paper PnL, hit rate, and max drawdown. Stop-loss now checks the
  cumulative (existing + this run) PnL, and `PARTIAL` results report
  `REVIEW_PARTIAL_STRATEGY` instead of a positive allocation recommendation.
- Public-source ingestion is re-run safe: observations upsert by natural
  primary key with first-seen `observed_at_utc`, ENTSOG reference snapshots
  replace only the ENTSOG scope and only when the new payload is non-empty
  (operator-maintained edges and mappings are never touched), and every run
  (success or failure) appends `audit_events` plus an `ingestion_runs` row.
  Expired runtime rows are pruned by retention policy (quotes 30d /
  observations 90d / opportunities 7d) via `scripts/ops/prune_runtime_data.py`.
- Backend-normalized market view: `GET /api/market/normalized` returns each
  market observation with backend-owned `hub`, `tenor`, `is_gas_price`, and
  `price_gbp_mwh` (latest-ECB-rate FX graph, max three conversion hops). The
  Web client's TypeScript re-implementation (`marketPriceNormalization.ts`)
  has been deleted; Strategy scenario assembly and the Market terminal
  consume backend-normalized rows and backend-owned `/api/market/spreads`
  (`from_hub`/`to_hub`/`spread_eur_mwh`), and contract tests forbid client-side
  FX/rate/spread math. The client performs no local persistence of business
  data; review actors stay in page memory only (R32 will add real identity).
- API contract evolution policy: `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`
  (additive-only `/api`, explicit deprecation process, no `/v1` aliases) is
  enforced by a pinned 84-path surface stability gate
  (`tests/contract/test_api_surface_stability.py`) so any path change fails CI
  until deliberately declared.
- Provider certification gate: licensed adapters can only be marked native
  live after operator-recorded `provider_certifications` evidence passes the
  simulated-to-live gate (stage `live_validated` with `simulated_shape_match`
  and `live_sample_validation` checks, written via the internal
  `POST /api/internal/sources/certification` endpoint with audit events).
  Uncertified licensed sources with records surface as `active_uncertified`
  and are never workflow-ready (fail closed, including when the DB is down).
- Minimal actor identity model: `docs/architecture/ACTOR_IDENTITY_MODEL.md`
  defines the operator principal (validated by
  `domain/identity/principal.normalize_principal`) recorded on review
  decisions, audit events, internal operator writes, and certification
  evidence. R32 adds PostgreSQL-backed USER/SERVICE identities with hashed
  bearer keys and roles; company SSO/OIDC remains deferred to R32A.
- R32 local identity governance: PostgreSQL `identity_principals` and
  `identity_api_keys` store USER/SERVICE identities with hashed bearer keys.
  Release-profile roles (VIEWER/ANALYST/OPERATOR/ADMIN) gate PUBLIC/READ,
  GOVERNED, and OPERATOR routes; per-identity commercial data scopes filter
  market observation/quote rows fail-closed; internal identity/key
  administration and audit export/retention endpoints are profile-gated.
  R32A adds OIDC access-token verification (lazy HTTPS discovery/JWKS, RS256,
  claim-to-role mapping) with no new dependency.
- Review workflow UI: the Review workspace now lists the persisted decision
  history and records `accepted` / `rejected` / `needs_attention` decisions
  with an optional note through `GET/POST /api/review/decisions`. The actor
  is an explicit page-level input (default `operator`), held in component
  memory only — the client persists no business data locally; a visible note
  states the actor is not yet SSO-authenticated (R32).
- Pipeline observability UI: the Runtime workspace renders the backend
  pipeline-health aggregation (per-source status/consecutive failures/last
  success, quote freshness over the last five minutes, open alerts, latest
  opportunity) from `GET /api/runtime/pipeline-health`; the top bar shows a
  data-mode badge driven by `streamingActive` (`Live push` on SSE,
  `Polling fallback` otherwise). The Sources workspace renders the provider
  certification gate (`unverified` / `simulation_matched` / `live_validated`
  badges, `active_uncertified` attention state with a `certify` next action).
- DB-backed portfolio network optimization:
  `POST /api/optimization/portfolio-network` composes upstream contracts,
  reference nodes, active route candidates, TSO access, effective tariffs,
  market observations, and as-of FX exclusively from PostgreSQL. The residual
  shared-capacity network-flow model allocates partial cheap-path capacity,
  reroutes remaining gas to alternate/local/other-market sales, and persists
  source ids, freshness, quality, assumptions, blockers, and contract-level
  PnL attribution in `optimization_runs`. Clients cannot submit network
  geometry, tariffs, capacities, or prices for this endpoint.
- R33 source operations: bounded exponential retry policies and per-source
  freshness SLAs now back the public ingestion worker; deployment scheduler
  ownership remains with the operator.
- R34 storage/nomination assessment: `POST /api/optimization/storage-dispatch`
  and `POST /api/optimization/nomination-window` expose the validated engines
  with run evidence. SANDBOX_SCENARIO supports explicit inputs;
  RUNTIME_DECISION composes storage facility/inventory/market/FX facts and
  nomination window masters from PostgreSQL (migration `0023`) and rejects
  client facility/window facts. No submission action exists.
- Typed domain ontology: `src/eurogas_nexus/domain/ontology/` is the single
  semantic-structure contract (controlled-vocabulary enums, action taxonomy with
  a forbidden-action boundary, typed concepts/relations, a computable-constraint
  registry). Scattered L5 constraints (TSO access, netback, stop-loss, allocation
  split) and route-cost/strategy enums are consolidated into it; the glossary is
  a display layer; the orphan `business_ontology_terms` table is decommissioned
  (migration `0016`).

## Active Workspaces

- Network: resource-pool map, persisted resources, route candidates, capacity
  blockers, route economics, PnL, and review warnings.
- Market: PostgreSQL-backed hub prices, tenors, spreads, ECB FX, source and
  simulation posture.
- Capacity: ENTSOG flow/capacity, TSO access, tariffs, GIE storage, and LNG.
- Resource Terms (`contracts` technical id): task-led Source/Terms/Pool
  impact/Library workflow with JSON/plain-text draft import, validation-gated
  PostgreSQL persistence, exact persisted impact, and per-resource route/cost
  semantics. Minimum-take/take-or-pay remains an explicit model gap.
- Scenario and Strategy: trader-reviewed calculations and shadow evaluation.
- Review: warnings, assumptions, source evidence, and report surfaces.
- Market Positioning: read-only external screen-order and indicative PnL
  observations, including `screen_order_observations`.
- Data Sources: source categories, credential maintenance, diagnostics,
  freshness, and ingestion history.
- Glossary, Runtime, Settings, and Manual: bilingual operating support.

## Optimization State

The stable operator-input endpoints are:

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
POST /api/optimization/portfolio-network
POST /api/optimization/storage-dispatch
POST /api/optimization/nomination-window
```

The first four endpoints accept operator-supplied sandbox inputs and return
the standard `data/meta` envelope. The fifth endpoint is DB-only
(`RUNTIME_DECISION`) and assembles every business input from PostgreSQL before
calling the shared-capacity network-flow engine; it never accepts client
geometry, tariffs, capacities, or prices. The network-flow module uses a true
residual network with reverse arcs, final-flow accounting, capacity checks,
and node-conservation checks. Storage dispatch and nomination-window
assessment remain validated internal prototypes.

## Deployment And Release State

- GitHub Actions validates Python, API import, Web, desktop, deployment assets,
  and the multi-architecture API image.
- Normal CI runs optimizer tests and builds desktop packages on pull requests.
- Local Windows package evidence was refreshed on 2026-09-01: the Tauri release
  executable and x64 Client-only NSIS installer built successfully, and the
  packaged Resource Terms Library/Pool Impact workflow was exercised against
  the PostgreSQL-backed API. This completes R15 packaging, not official V1
  release acceptance.
- Every `main` push runs the release workflow for Web, Windows Client-only,
  Windows AllInOne, Linux x64, Linux ARM64, the Server operator bundle, and the
  amd64/arm64 runtime image.
- Linux Tauri dependency installation uses the official HTTPS Ubuntu mirror and
  bounded retries to tolerate transient ARM runner mirror failures.
- Customer production signing certificates are not stored in this repository.

## Web Application Architecture

The React composition root is now nine lines and only creates the application
controller and shell. Stateful workflows live under `app/hooks`, derived
portfolio decision state lives under `app/model`, persistent chrome lives under
`app/shell`, and workspace selection lives under `app/workspaces`. Contract
tests enforce the small root and inspect the real module owners instead of
requiring all behavior to appear in `App.tsx`.

See [WEB_APPLICATION_ARCHITECTURE-EN.md](../clients/WEB_APPLICATION_ARCHITECTURE-EN.md).

## Remaining Release Limitations

1. OIDC interactive login flows (redirect/PKCE/refresh/session) and SAML
   remain deferred. R32/R32A local identity, role authorization, commercial
   scopes, and audit governance are delivered; server roles stay
   private-network/VPN-only until security acceptance.
2. Commercial providers remain gated by customer credentials, entitlement,
   licenses, and operator validation.
3. Public-source retry/backoff and freshness SLAs are delivered (R33);
   deployment scheduler ownership, licensed-provider production runs, and
   production alert-delivery channels remain deployment work.
4. Portfolio-wide optimization now composes contracts, routes, tariffs,
   capacities, TSO access, and FX from PostgreSQL and attributes PnL at
   contract level. Production hardening of source scheduling, alert delivery,
   and export governance remains in R33.
5. Storage/nomination assessment workflows are customer-facing for review
   (R34); automated security-acceptance evidence passes, but external
   deployment review is still required.
6. Orders and PnL are imported observations; no order entry, amendment,
   cancellation, routing, execution, or trade capture is performed.

## Next Work

Follow [NEXT_DEVELOPMENT_QUEUE.md](NEXT_DEVELOPMENT_QUEUE.md). Remaining work
is external security acceptance (penetration test, OIDC TLS review,
backup/restore drill, owner sign-off) before removing the
private-network/VPN-only posture. S4.3 `/api/workflows/*` removal is complete.
