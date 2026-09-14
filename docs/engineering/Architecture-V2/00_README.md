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
