# Next Development Queue

Chinese companion: [NEXT_DEVELOPMENT_QUEUE-CN.md](NEXT_DEVELOPMENT_QUEUE-CN.md)

## Queue Rule

Execute the first pending increment. Each increment requires an ExecPlan,
tests, bilingual operator documentation, and honest `PARTIAL`/`BLOCKED` status.
Do not skip DB, source-lineage, entitlement, or human-review boundaries to add a
visible client feature.

## Current Baseline

Status: `complete-in-current-worktree`

- PostgreSQL/Alembic schema through `0023_storage_nomination_masters`.
- Stable public `/api`; profile-gated `/api/internal` and `/api/dev`.
- Python SDK and CLI.
- React/Vite Web workspace and Tauri Windows/Linux desktop clients.
- Map-first resource pool, Market, Capacity, Contracts, Strategy, Review,
  Market Positioning, Sources, Glossary, Runtime, Settings, and Manual.
- Server, Client, and AllInOne deployment roles.
- Automated Web, Windows x64, Linux x64/ARM64, deployment-bundle, and
  multi-architecture runtime-image release workflow.

## Delivered Increments

### R22-R28: Client And Runtime Hardening

Status: `complete-in-current-worktree`

Delivered documentation alignment, cockpit decomposition, source-shaped
simulated market feeds through PostgreSQL, market/capacity/source workspaces,
backend-owned contracts, runtime data correctness, and client/release
hardening. Historical ExecPlans remain under `.agent/plans/` as implementation
evidence.

### R29: Deployment Roles

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R29_DEPLOYMENT_ROLES_EXECPLAN.md`

Delivered explicit Server, Client, and AllInOne roles, private-network preview
enforcement, managed client API configuration, runtime containers, recurring
public ingestion workers, and release packaging.

### R30: Optimization Correctness And Release Gate

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R30_OPTIMIZATION_CORRECTNESS_EXECPLAN.md`

Delivered a correct residual-network natural-gas flow optimizer, explicit
storage/nomination input validation, standard optimization API envelopes,
optimizer coverage in all normal validation commands, and resilient Linux ARM
release dependency installation.

### R30A: Web Application Architecture

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R30A_WEB_APPLICATION_ARCHITECTURE_EXECPLAN.md`

Reduced `App.tsx` to a composition root and established explicit hook, model,
shell, and workspace-renderer ownership. Updated owner-based contract tests and
added bilingual implementation documentation. This maintenance increment does
not replace or alter the pending R31 DB-backed optimization scope.

### R30B: Intraday Decision Feed

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R30B_INTRADAY_DECISION_FEED_EXECPLAN.md`

Delivered normalized L1 quote and company TSO-access tables, backend-owned
route-adjusted opportunity scanning, immutable decision snapshots, explicit
expiry behavior, stable API and SDK reads, 10-second client refresh, and a
compact Network/Market decision feed. Simulated providers use the same database
contract as future licensed adapters. This route-level feed does not replace
the pending R31 portfolio allocation scope.

### R30C: Visible LLM Monitoring And Interaction

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R30C_LLM_MONITORING_EXECPLAN.md`

Delivered a deduplicated PostgreSQL alert lifecycle, 10-second monitoring
worker, visible top-bar Alert Center, acknowledgement, explicit per-alert
dialogue, encrypted DeepSeek credential handling, live connection diagnostics,
and real DeepSeek runtime calls. Deterministic engines remain responsible for
facts and triggers; the LLM only explains persisted evidence and never executes
business actions.

### R30D: Strategy Shadow-Run Persistence And Correctness

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R31_STRATEGY_SHADOW_RUN_PERSISTENCE_EXECPLAN.md`

Delivered DB-backed shadow-run persistence (`strategy_runs` and
`strategy_allocation_targets`), read-only run history and cumulative summary
endpoints, cumulative paper PnL / hit-rate / max-drawdown aggregation, corrected
cumulative stop-loss accounting, honest `PARTIAL` candidate action, legacy
`elapsed_days` semantics, SDK/CLI methods, and Web risk-control editing with
run history and cumulative performance display.

### ONT-M1: Typed Domain Ontology And Constraint Consolidation

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/ONT_M1_L5_CONSTRAINTS_EXECPLAN.md`

Delivered a rigorous, typed domain ontology (`src/eurogas_nexus/domain/ontology/`)
as the single semantic-structure contract: controlled-vocabulary enums, an
action taxonomy with a forbidden-action boundary, typed concepts/relations, and
a computable-constraint registry delegating to `domain/constraints/`. Consolidated
the scattered L5 constraints (TSO access, netback, stop-loss, allocation split)
and the route-cost/strategy enums into one home, rewired `business_logic_ontology()`
to derive from the ontology, down-graded the glossary to a display layer, and
decommissioned the orphan `business_ontology_terms` table (migration `0016`).

### R31: DB-Backed Portfolio Network Optimization

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R31_DB_PORTFOLIO_NETWORK_EXECPLAN.md`

Delivered `POST /api/optimization/portfolio-network` plus SDK method
`optimize_portfolio_network`. The endpoint composes upstream contracts,
reference nodes, active route candidates, TSO access, effective tariffs,
market observations, and as-of FX exclusively from PostgreSQL, then runs the
residual shared-capacity network-flow model. Final flows are decomposed into
source-to-sale paths with contract-level PnL attribution, and every run
persists its assembled inputs, lineage, assumptions, blockers, and source ids
in `optimization_runs`. Missing, stale, or incompatible facts fail closed.

Goal: connect the validated shared-capacity model to persisted commercial and
infrastructure facts without letting clients fabricate inputs.

Required work:

- compose upstream contracts/resources from PostgreSQL;
- compose sale opportunities from PostgreSQL market observations;
- join route topology, directional available capacity, TSO access, and tariff
  validity by gas day/product;
- allocate partial cheap-path capacity and re-evaluate remaining gas against
  alternate routes and local/other-market sale options;
- preserve source IDs, observation times, freshness, quality, assumptions,
  blockers, and contract-level PnL attribution;
- add API DTOs and SDK methods only after the DB composition contract is fixed;
- keep all outputs trader-reviewed and non-executable.

Acceptance:

- no client-provided network geometry, tariff, or capacity is authoritative;
- missing/stale/incompatible facts block or qualify optimization explicitly;
- shared capacities and TSO access are enforced across the portfolio;
- API, SDK, integration, optimization, and contract tests pass.

## R32: Authentication, Entitlement, Audit, And Export Governance

Status: `partial-in-current-worktree`

ExecPlan: `.agent/plans/V1_R32_IDENTITY_AUTH_GOVERNANCE_EXECPLAN.md`

Goal: make server deployments suitable for authenticated multi-user use.

Delivered:

- Local PostgreSQL identity model (`identity_principals`,
  `identity_api_keys`, migration `0022`) with USER/SERVICE principals, hashed
  bearer keys, and VIEWER/ANALYST/OPERATOR/ADMIN roles.
- Release-profile role authorization: READ/PUBLIC require VIEWER+, GOVERNED
  requires ANALYST+, OPERATOR requires OPERATOR+.
- Per-identity commercial-data scopes with fail-closed unknown-family checks
  and row filtering on market observation/quote surfaces.
- Internal identity/key administration and bounded audit export with audit
  retention pruning (default 365 days, dry-run first).
- R32A OIDC access-token verification: lazy HTTPS discovery/JWKS, RS256
  signature/issuer/audience/expiry checks, role and entitlement claim mapping,
  with no new Python dependency.

Remaining:

- OIDC interactive login flows (redirect/PKCE/refresh/session) and SAML, if a
  deployment requires browser SSO rather than access-token SSO.
- Security acceptance must pass before the private-network/VPN-only server
  posture is removed.

Required work:

- select and document the supported identity model;
- enforce authorization on operator, credential, portfolio, report, and export
  surfaces;
- fail closed for unknown commercial-data entitlement;
- expand audit coverage and retention controls;
- remove the private-network-only limitation only after security acceptance.

## R33: Production Source Operations

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R33_PRODUCTION_SOURCE_OPERATIONS_EXECPLAN.md`

Goal: productionize public and licensed ingestion scheduling, retries, alerts,
freshness SLAs, and operator diagnostics without client-side provider calls.

Delivered: `application/source_operations.py` owns bounded exponential retry
policies and per-source freshness SLAs; `run_public_ingestion_worker.py`
supports `--retry-max` / `--retry-backoff-seconds` and keeps supervision alive
after failures. Deployment scheduler ownership remains with the operator
(systemd/Kubernetes/Windows task); licensed providers remain gated by
credentials, entitlement, and provider certification.

## R34: Network Flow, Storage, And Nomination Client Workflows

Status: `complete-in-current-worktree`

ExecPlan: `.agent/plans/V1_R34_STORAGE_NOMINATION_CLIENT_WORKFLOWS_EXECPLAN.md`
and `.agent/plans/V1_R34A_STORAGE_NOMINATION_RUNTIME_SECURITY_ACCEPTANCE_EXECPLAN.md`

Goal: expose validated models only after R31-R33 provide DB-owned inputs,
lineage, authorization, and operational reliability. Nomination remains
assessment-only; no submission action is permitted.

Delivered: `POST /api/optimization/storage-dispatch` and
`POST /api/optimization/nomination-window` with SDK methods. SANDBOX_SCENARIO
supports explicit assessment inputs; RUNTIME_DECISION composes storage
facility/inventory/market/FX facts and nomination window masters from
PostgreSQL (migration `0023`, three tables) and rejects client facility/window
facts. Nomination returns accepted/adjusted quantities only; no submission
action exists. Automated security-acceptance evidence is executable via
`scripts/security/run_security_acceptance.py`; external deployment review
remains required before removing the private-network/VPN-only posture.
