# Next Development Queue

Chinese companion: [NEXT_DEVELOPMENT_QUEUE-CN.md](NEXT_DEVELOPMENT_QUEUE-CN.md)

## Queue Rule

Execute the first pending increment. Each increment requires an ExecPlan,
tests, bilingual operator documentation, and honest `PARTIAL`/`BLOCKED` status.
Do not skip DB, source-lineage, entitlement, or human-review boundaries to add a
visible client feature.

## Current Baseline

Status: `complete-in-current-worktree`

- PostgreSQL/Alembic schema through `0015_llm_monitoring_alerts`.
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

## R31: DB-Backed Portfolio Network Optimization

Status: `pending`

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

Status: `pending`

Goal: make server deployments suitable for authenticated multi-user use.

Required work:

- select and document the supported identity model;
- enforce authorization on operator, credential, portfolio, report, and export
  surfaces;
- fail closed for unknown commercial-data entitlement;
- expand audit coverage and retention controls;
- remove the private-network-only limitation only after security acceptance.

## R33: Production Source Operations

Status: `pending`

Goal: productionize public and licensed ingestion scheduling, retries, alerts,
freshness SLAs, and operator diagnostics without client-side provider calls.

## R34: Network Flow, Storage, And Nomination Client Workflows

Status: `pending`

Goal: expose validated models only after R31-R33 provide DB-owned inputs,
lineage, authorization, and operational reliability. Nomination remains
assessment-only; no submission action is permitted.
