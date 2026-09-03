# Infrastructure Connector Contract

## Purpose

External system, object store, and secret-provider adapters are not
materialized as empty source packages. Active external-facing connector work
lives under `src/eurogas_nexus/ingestion/connectors/`; when a dedicated
infrastructure adapter package is needed, it is created with its first
implementation.

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
