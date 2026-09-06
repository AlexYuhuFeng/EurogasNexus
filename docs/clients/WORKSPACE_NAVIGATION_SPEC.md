# Workspace Navigation Spec

## Decision

Eurogas Nexus exposes five primary professional workspaces in the persistent
topbar. Each primary workspace owns a compact local task switcher where needed.
The old grouped-menu/page-tab duplication is removed.

Technical workspace ids remain stable during the compatibility period. In
particular:

- `contracts` is displayed as `Resource Terms`.
- `orders` is displayed as `Market Positioning`.
- `glossary` remains a technical workspace and deep link, re-homed under System.

## Primary workspaces

| Primary | Children | Default | Purpose |
|---|---|---|---|
| Market | Network, Market, Capacity | Network | What is happening physically and financially? |
| Portfolio | Resource Terms, Market Positioning | Resource Terms | What resources/exposures do we currently have? |
| Strategy Lab | Strategy | Strategy | What research strategy are we testing/monitoring? |
| Decision Center | Scenario, Review | Scenario | What scenario/optimization output needs human review? |
| System | Data Sources, Runtime, Settings, Manual, Glossary | Data Sources | Is the data/application configured and healthy? |

The primary workspace is derived from the technical view id; it is never a
second URL namespace.

## Ordering

The visible global order is:

```text
Market
Portfolio
Strategy Lab
Decision Center
System
```

Local task order follows the child tables above. Strategy Lab has one child and
therefore renders no local task switcher until later strategy subviews land.

## Compatibility

Deep links continue to use existing workspace ids:

```text
network
capacity
market
contracts
orders
strategy
scenario
review
sources
runtime
settings
manual
glossary
```

A later route-migration milestone may add `resource-terms` and
`market-positioning` aliases, but it should preserve `contracts` and `orders` as
backward-compatible query values.
