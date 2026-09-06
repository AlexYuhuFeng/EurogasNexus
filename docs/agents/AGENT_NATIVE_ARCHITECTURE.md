# Agent-Native Architecture (CR-15 / P14)

## Goal

Eurogas Nexus becomes an agent-native research operating system without
becoming "an LLM wired directly to a database". Business/domain capabilities
remain first-class and usable by API, SDK, and MCP. MCP is one adapter.

```
DOMAIN / APPLICATION CAPABILITIES
            ↓
      Capability Registry
            ↓
    ┌───────┼────────┐
    ▼       ▼        ▼
   MCP     API      SDK
    │
    ▼
Agent Runtime
```

## Responsibility split

| Owner | Responsibility |
|---|---|
| Deterministic domain services | entity resolution, market/network/capacity/portfolio/route/scenario/optimization evidence, dataset build, strategy validation, backtest, robustness calculations |
| Capability Registry | metadata: schema, version, determinism, side effects, permissions, entitlement, freshness, provenance, timeout/retry, policy class |
| LLM | research objective interpretation, plan/hypothesis drafting, structured findings synthesis, Strategy IR drafting, challenge questions, final explanation |
| Agent Runtime | governed state machine, tool invocation trace, budgets, human-confirmation gates, artifact linking |
| Human | freeze/start/pause decisions, review decisions, final acceptance |

## MCP boundary

- MCP receives JSON-RPC and maps to registered capabilities.
- MCP contains no calculation or persistence logic.
- Each call carries principal, permissions, entitlements, and correlation id.
- No SQL, no database table names, no execution tools.

## Research artifacts

- `ResearchPlan` — validated analytical objective and evidence requirements.
- `ResearchFinding` — structured statistic, sample, period, method, evidence.
- `StrategyIR` — constrained, serializable strategy specification.
- `StrategyVersion` (CR-03) — immutable compiled domain definition.
- `BacktestResult` (CR-04) — deterministic result.
- `ChallengeReport` — adversarial structured review.
- `ReviewPack` — human-review evidence bundle.
- `AgentRun` — observable orchestration trace, never hidden chain-of-thought.

## Orchestration state machine

`OBJECTIVE_RECEIVED → PLAN_DRAFTED → PLAN_VALIDATED → DATA_ANALYSIS →
HYPOTHESIS_FORMED → STRATEGY_SPEC_DRAFTED → STRATEGY_VALIDATED → BACKTESTED →
ROBUSTNESS_EVALUATED → CHALLENGED → READY_FOR_HUMAN_REVIEW`, plus
`BLOCKED`, `FAILED`, and `CANCELLED`.

Action policy classes:

- `AUTO_ALLOWED` — read evidence, deterministic analytics.
- `AGENT_ALLOWED_WITHIN_RESEARCH` — draft plan/finding/strategy.
- `HUMAN_CONFIRMATION` — freeze version, start/pause/resume shadow.
- `HUMAN_ONLY` — record review decisions.

## Entitlement and security

- The agent inherits the authenticated user principal. There is no AI-admin.
- Every capability invocation is authorization-checked and, where declared,
  entitlement-checked.
- External LLM payloads follow the existing licensed-data and sensitive-field
  filtering rules.
- Provider text and documents are untrusted input, never system instructions.
- No execution/order/nomination capability exists in the registry.

## Observability

AgentRun and ToolInvocation rows persist observable trace data: capability,
capability version, input hash, safe summary, status, output reference,
evidence refs, error code, and duration. Hidden chain-of-thought is never
stored.
