# Infrastructure Connector Contract

## Purpose

`src/eurogas_nexus/infrastructure` owns future adapters for external systems,
object stores, and secrets providers.

## Bootstrap State

The connector, object store, and secrets packages are inert. No live connector
exists.

## Rules

- Interfaces must be defined before live adapters.
- Live adapters must never execute at import time.
- External calls must be explicit, observable, timeout-bound, and testable with
  fakes.
- Secrets access must be dependency-injected and auditable.
- Connectors must not perform analytics.
- Connectors may fetch, normalize, and expose source metadata through explicit
  interfaces once approved.

## Forbidden In Bootstrap

- Live data provider connectors.
- External API calls.
- LLM provider calls.
- Company SSO/OIDC integration.
