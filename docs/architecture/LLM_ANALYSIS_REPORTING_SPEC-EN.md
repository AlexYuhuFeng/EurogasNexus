# LLM Analysis And Reporting Spec - EN

## V1 Decision

DeepSeek is the first supported live LLM provider for V1. OpenAI and
other providers remain credential/provider slots until later milestones add and
test adapters.

LLM calls are never made at import time, during tests, or directly from Web,
Windows, SDK, or CLI clients. The only allowed live path is:

```text
Client -> /api -> backend analysis route -> backend credential store -> DeepSeek
```

## Credential Rule

Users may enter a DeepSeek API key through the provider credential UI/API. The
backend stores it encrypted in PostgreSQL. Plaintext keys are write-only and are
never returned to clients, logs, reports, or tests.

Credential provider IDs:

- `DEEPSEEK`: preferred V1 LLM provider;
- `LLM`: legacy/generic fallback credential slot.

## Analysis Capabilities

V1 analysis supports:

- DB inquiry over backend snapshots;
- business-logic ontology explanation;
- glossary Q&A;
- PnL tracking readiness and warnings;
- TSO operation status reports;
- portfolio/resource/contract reports;
- market movement synthesis;
- strategy run and shadow-run context summaries.

LLM providers are not the source of truth. The source of truth remains
PostgreSQL. The provider receives a structured snapshot, not direct DB access.

## Report Generation

Reports must include:

- current portfolio or selected resources/contracts;
- strategy in place and strategy run state;
- historical PnL since selected strategy/portfolio effective time when persisted
  PnL series exists;
- related market prices, quantities, FX, route costs, flows, storage, LNG, and
  warnings for the selected duration;
- candidate market decision-support commentary with citations.

Reports must include source references, missing inputs, warnings,
`research_only`, and `human_review_required`.

## Glossary Integration

Glossary terms may expose operational context through:

```text
GET /api/glossary/{term}/context
```

Examples:

- Zeebrugge Entry Point, GATE LNG, or TTF: description, capacity, capacity
  usage for the selected snapshot/duration, related hub/screen/assessment
  prices, route options, and source status.
- ICIS Heren: assessment description, license warning, related prices, and
  market-source context.

If runtime DB data is unavailable, the endpoint must return partial context with
clear warnings rather than inventing customer data.

## Current Endpoints

```text
GET  /api/analysis/ontology
POST /api/analysis/query
POST /api/reports/portfolio
GET  /api/glossary/{term}/context
```

## Internet Requirement

Internet is required only when `invoke_provider=true` and a DeepSeek credential
is configured. Offline development and tests use deterministic snapshot output
and must not call any LLM provider.
