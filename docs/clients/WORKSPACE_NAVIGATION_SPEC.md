# Workspace Navigation Spec

## Decision

Eurogas Nexus uses grouped workspace navigation rather than a flat list of pages.
The visible menu should make the product workflow clear before exposing all
secondary tools.

Technical workspace ids remain stable during the compatibility period. In
particular:

- `contracts` is displayed as `Resource Terms`.
- `orders` is displayed as `Market Positioning`.

## Menu Groups

### Decision Workspace

Primary workflow surfaces:

1. Network
2. Scenario
3. Review

These pages answer the core workflow questions: what resources exist, what route
or sale scenario is being tested, and what decision-support output should be
reviewed by a human.

### Commercial Inputs

Commercial and market-context surfaces:

1. Resource Terms
2. Market
3. Capacity
4. Market Positioning

Resource Terms captures EFET-style resource assumptions for the resource-pool
optimizer. It is not an ETRM contract master, official booking workflow,
settlement system, or approval workflow.

Market Positioning displays imported screen observations and portfolio PnL
snapshots. It is read-only imported context and must not become order entry,
order routing, trade capture, nomination submission, or execution.

### Analytics

Analysis and explanation surfaces:

1. Strategy
2. Glossary

Strategy remains a paper/shadow-run and decision-support surface. Glossary
explains operational terms and DB-derived context.

### Operations

Operator and support surfaces:

1. Data Sources
2. Runtime
3. Settings
4. Manual

These pages support source posture, runtime readiness, local preferences, and
user guidance. They should not dominate the first-run decision workflow.

## Ordering

The visible order is:

```text
Decision Workspace
- Network
- Scenario
- Review

Commercial Inputs
- Resource Terms
- Market
- Capacity
- Market Positioning

Analytics
- Strategy
- Glossary

Operations
- Data Sources
- Runtime
- Settings
- Manual
```

## Compatibility

Deep links continue to use existing workspace ids:

```text
network
scenario
review
contracts
market
capacity
orders
strategy
glossary
sources
runtime
settings
manual
```

A later route-migration milestone may add `resource-terms` and
`market-positioning` aliases, but it should preserve `contracts` and `orders` as
backward-compatible query values.
