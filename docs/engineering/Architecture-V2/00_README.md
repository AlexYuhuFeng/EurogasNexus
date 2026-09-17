# Eurogas Nexus Architecture V2 — Final Reviewed Implementation Pack

Status: **Target Architecture / Binding Implementation Baseline**

This pack consolidates the full architecture review and supersedes the earlier draft V2 packs.

It is intended to be handed directly to **DeepSeek Harness** for staged implementation.

## 1. Product abstraction

Eurogas Nexus is an enterprise-grade **European Gas Decision Intelligence Platform**.

Its purpose is to help authorised users:

1. **KNOW** — understand European gas market and physical-system state.
2. **UNDERSTAND** — understand portfolio, resource, contract, capacity and exposure context.
3. **EXPLORE** — test scenarios, assumptions and alternatives.
4. **OPTIMISE** — evaluate constrained commercial alternatives using deterministic engines.
5. **DECIDE** — create reproducible, reviewable, human-owned decision evidence.

It is **not** an ETRM, order-entry system, nomination-submission system, settlement system,
auto-trading system or official recommendation engine.

## 2. Core V2 thesis

The current project already has strong backend, data, release and research foundations.
The largest remaining gap is not “more features”; it is **architecture convergence and professional
product experience**.

The target is:

**One Platform · One Primary Web UI · Multiple Experiences · Multiple Hosts**

with:

- unified Data Platform;
- effective-access model;
- overlapping functional assignments and work modes;
- separate Business User Plane and Control Plane;
- Active Context;
- Analysis Snapshot;
- Decision Case;
- application projection/query layer;
- governed AI;
- professional release/deployment/operations/support;
- a coherent Product Experience Architecture across Web and Desktop.

## 3. Reading order

1. `01_EXECUTIVE_REVIEW.md`
2. `02_ARCHITECTURE_CONSTITUTION.md`
3. `03_TARGET_PLATFORM_ARCHITECTURE.md`
4. `04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`
5. `05_CLIENT_HOST_CROSS_PLATFORM.md`
6. `06_IDENTITY_ACCESS_CONTROL_PLANE.md`
7. `07_DATA_PLATFORM.md`
8. `08_DECISION_APPLICATION_AI.md`
9. `09_PRODUCT_OPERATIONS_RELEASE_SUPPORT.md`
10. `10_DOCUMENTATION_NFR_TESTING.md`
11. `11_CURRENT_TO_TARGET_GAP_MATRIX.md`
12. `12_MIGRATION_ROADMAP.md`
13. `13_DEEPSEEK_HARNESS_MASTER_PROMPT.md`
14. `14_VALIDATION_PACK.md`

## 4. Execution rule

Do **not** implement all waves in one run.

DeepSeek Harness must:
- inspect the current repository first;
- preserve proven behaviour;
- identify conflicts with accepted ADRs;
- execute the first approved migration wave only;
- stop and report evidence before proceeding.

The architecture is evolutionary, not a big-bang rewrite.

## Codex + DeepSeek autonomous execution

For the recommended low-cost autonomous workflow, start with `CODEX_ENTRYPOINT.md`.

The preferred division of labour is:
- **GPT-6 Astra**: lightweight architecture planning, decomposition, integration review and wave acceptance.
- **DeepSeek Flash V4.1**: primary implementation worker through DeepSeek Harness Desktop or another approved execution path.

See:
- `15_CODEX_AUTONOMOUS_ORCHESTRATOR.md`
- `16_MODEL_ROUTING_POLICY.md`
- `17_EXECUTION_STATE_AND_RESUME_PROTOCOL.md`
- `18_DEEPSEEK_WORKER_PROTOCOL.md`

The V2 architecture remains authoritative; these files define how to execute it economically and
resumably.

## 5. Programme artefacts delivered

The pack above is the target architecture. The programme's own evidence and contracts are recorded
alongside it, and the resumable state lives in the execution checkpoint.

- [Autonomous execution policy](AUTONOMOUS_EXECUTION_POLICY.md) — highest operational authority.
- [Authority reconciliation proposal](AUTHORITY_RECONCILIATION_PROPOSAL.md) — historical; superseded
  by ADR-0016.
- [Execution state and checkpoint](../ARCHITECTURE_V2_EXECUTION_STATE.md) — resumable programme
  state; read this before planning work.

Wave 0 (baseline and architecture freeze):

- [W0-01 client inventory](W0-01_CLIENT_INVENTORY.md) — routes, workspaces, panels, navigation and
  client API dependencies, accepted after repair.
- [W0-02 backend access inventory](W0-02_BACKEND_ACCESS_INVENTORY.md) — identity, capability,
  entitlement, provider and control-plane current behaviour.
- [W0-03 architecture reconciliation](W0-03_ARCHITECTURE_RECONCILIATION.md) — conflict register,
  current-to-target map and the Wave 0 gate.
- [W0-03 fitness gaps](W0-03_FITNESS_GAPS.md) — coverage of the V2 architecture fitness functions.

Wave 1 (product experience architecture foundation):

- [W1-01 shell and Active Context contract](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md)
- [W1-02 workspace pattern and panel registry](W1-02_WORKSPACE_PATTERN_AND_PANEL_REGISTRY.md)
- [W1-03 Inspector, AI actions and command palette](W1-03_INSPECTOR_AI_AND_COMMAND_CONTRACT.md)
- [W1-04 HostCapabilities contract](W1-04_HOST_CAPABILITIES_CONTRACT.md)
- [W1-05 canonical experience specifications](W1-05_CANONICAL_EXPERIENCE_SPECS.md)

Machine-readable form of the Wave 1 contracts: `clients/web/src/app/experience/` and
`clients/web/src/app/host/`, with focused checks in
`clients/web/tests/experienceArchitecture.test.ts`.

Wave 2 (effective access and experience composition):

- [W2-01 effective access and the ExperienceProfile](W2-01_EFFECTIVE_ACCESS_AND_EXPERIENCE_PROFILE.md) —
  capability catalogue, platform-administration/commercial-data separation, and the
  composition contract served inside `GET /api/me`.

Wave 3 (control plane separation):

- [W3-01 control plane separation](W3-01_CONTROL_PLANE_SEPARATION.md) — the
  capability-gated Administration surface, the restricted control-plane notice and
  the preserved deep links.

Wave 4 (unified data platform):

- [W4-01 unified data platform surface](W4-01_UNIFIED_DATA_PLATFORM.md) — the
  declared business-facing Data Product catalogue with its per-principal
  entitlement and freshness posture, and Analysis Snapshot v1 as the persisted
  reproducibility reference cited by produced results.

Wave 5 (application projections):

- [W5-01 application projections](W5-01_APPLICATION_PROJECTIONS.md) — MarketContext,
  PortfolioSnapshot, ReviewContext and ScenarioContext, with the market/portfolio
  read layer extracted so a projection cannot diverge from the route it composes.

Wave 6 (Decision Case):

- [W6-01 Decision Case and Decision Record](W6-01_DECISION_CASE.md) — the container
  for objective, context, assumptions, alternatives, evidence and human review, and
  the record that is evidence rather than execution approval.

Wave 7 (research/AI convergence):

- [W7-01 canonical AI actions](W7-01_CANONICAL_AI_ACTIONS.md) — the five declared AI
  actions as a real cross-workspace surface: evidence-gated, run over the existing
  analysis route, qualified as interpretation with no numeric authority, and
  mounted inside the command palette rather than a new page.

Wave 8 (product operations):

- [W8-01 product error taxonomy](W8-01_ERROR_TAXONOMY.md) — ten families, stable
  codes, severity and recoverability, correlation ids, and operator-only detail.
- [W8-02 unified job model](W8-02_UNIFIED_JOB_MODEL.md) — one lifecycle for
  ingestion, dataset builds, optimisation, backtests, reporting and agent runs,
  with a tracking seam existing work can adopt.

Wave 9 (UI implementation convergence):

- [W9-01 shell surfaces](W9-01_SHELL_SURFACES_INSPECTOR_AND_PALETTE.md) — the
  canonical Inspector region and the mounted command palette, with the remaining
  page migrations named explicitly.
