# Decision, Application and AI Architecture

## 1. Decision Platform

Target structure:

```text
Decision Case
├── Objective
├── Active Context
├── Analysis Snapshot
├── Assumptions
├── Alternatives
├── Scenarios
├── Economics / Optimisation
├── Risk / Constraints
├── Evidence
├── AI Findings / Challenge
├── Human Review
└── Decision Record
```

Decision Record is evidence/rationale, not execution approval.

## 2. Application projections

Preserve current endpoint compatibility but add coherent application read models.

Recommended:
- MarketContext
- PortfolioSnapshot
- RouteDecisionContext
- ScenarioContext
- StrategyEvidence
- DecisionCaseProjection
- ReviewContext
- ManagementOverview

## 3. Strategy lifecycle

Target lifecycle:

`Research Question -> Hypothesis -> Strategy Draft -> Dataset -> Backtest -> Robustness ->
Benchmark -> Challenge -> Freeze -> Shadow -> Review -> Retire/Promote`

Do not create one independent top-level page for each object.

## 4. AI position

AI is cross-workspace, not a separate island.

AI may:
- interpret objectives;
- draft research plans;
- identify evidence;
- draft hypotheses;
- draft StrategyIR;
- compare alternatives;
- challenge assumptions;
- explain deterministic results;
- prepare review packs/reports.

AI may not:
- invent missing data;
- bypass entitlement;
- own PnL/optimisation truth;
- execute trades;
- change protected state without required gates.

## 5. Unified Job

Common states:
QUEUED, RUNNING, WAITING_FOR_INPUT, SUCCEEDED, FAILED, CANCELLED, EXPIRED.

Fields:
- job_id/type/version;
- principal;
- scope;
- snapshot_id;
- input hash;
- progress;
- status;
- start/finish;
- output refs;
- error code;
- retry/cancel;
- correlation_id;
- provenance.

Use where appropriate for ingestion, optimisation, dataset build, backtest, reporting and agent work.

## 6. Error taxonomy

Families:
AUTH, ENTITLEMENT, VALIDATION, DATA, CALCULATION, DEPENDENCY, CONFIGURATION, JOB, AGENT, SYSTEM.

Example codes:
- DATA_STALE
- DATA_MISSING
- ENTITLEMENT_DENIED
- PORTFOLIO_INCOMPLETE
- ROUTE_INFEASIBLE
- OPTIMIZATION_INFEASIBLE
- PROVIDER_UNAVAILABLE
- SNAPSHOT_EXPIRED
- AGENT_BUDGET_EXCEEDED

Error response:
- stable code;
- user-safe message;
- severity;
- recoverability;
- suggested action;
- correlation ID;
- operator detail only on authorised operator surfaces.
