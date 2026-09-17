# Workspace Navigation Spec

## Decision

Eurogas Nexus exposes six primary professional workspaces in the persistent
topbar: five business workspaces plus the capability-gated Administration
surface. Each primary workspace owns a compact local task switcher where needed.
The old grouped-menu/page-tab duplication is removed.

Architecture V2 (ADR-0016, `06_IDENTITY_ACCESS_CONTROL_PLANE.md` section 8)
separates the business workspace from the control plane, so provider, credential,
runtime and access administration no longer sit inside a business primary.

Technical workspace ids remain stable during the compatibility period. In
particular:

- `contracts` is displayed as `Resource Terms`.
- `orders` is displayed as `Market Positioning`.
- `glossary` remains a technical workspace and deep link, re-homed under System.
- `sources`, `runtime` and `access` keep their ids and deep links but are owned by
  Administration instead of System.

## Primary workspaces

| Primary | Children | Default | Purpose |
|---|---|---|---|
| Market | Network, Market, Capacity | Network | What is happening physically and financially? |
| Portfolio | Resource Terms, Market Positioning | Resource Terms | What resources/exposures do we currently have? |
| Strategy Lab | Strategy | Strategy | What research strategy are we testing/monitoring? |
| Decision Center | Scenario, Review | Scenario | What scenario/optimization output needs human review? |
| System | Research Data, Agent Research, Settings, Manual, Glossary | Research Data | What governed data, research and preferences are available? |
| Administration | Data Sources, Runtime, Access & Identity | Data Sources | Are providers, runtime and access configured and healthy? |

The primary workspace is derived from the technical view id; it is never a
second URL namespace.

## Administration is capability-gated

Administration is a control-plane surface, not a business workspace:

- The topbar offers the Administration primary only when the authenticated
  identity's composition (`GET /api/me` → `experience.effective_capabilities`)
  includes an administration capability: `access.manage`, `api_keys.manage`,
  `provider.ingestion.operate`, `provider.backfill.operate`,
  `provider.credential.manage` or `provider.certification.manage`.
- Reading source or runtime *status* is not administration: every role keeps the
  data-source and runtime indicators in the business shell.
- A deep link into `sources`, `runtime` or `access` without that capability
  renders a bounded restricted notice instead of the workspace.
- This is presentation, and it fails closed (an absent profile hides the surface).
  It is **not** a security boundary: the backend authorises every request, and a
  platform-administration identity without a commercial role is refused commercial
  data with `403 commercial_access_not_granted`.

## Ordering

The visible global order is:

```text
Market
Portfolio
Strategy Lab
Decision Center
System
Administration   (only with an administration capability)
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
access
research
agents
```

A later route-migration milestone may add `resource-terms` and
`market-positioning` aliases, but it should preserve `contracts` and `orders` as
backward-compatible query values.
