# Application Workflow Contract

## Purpose

`src/eurogas_nexus/application/workflows` will coordinate domain behavior,
repository access, data quality checks, and infrastructure interfaces.

## Rules

- Workflows orchestrate; they do not own persistence adapters.
- Workflows may depend on domain models and abstract infrastructure interfaces.
- Workflows must be explicit about user intent, audit events, and entitlement
  checks once those layers exist.
- Workflow tests belong under `tests/workflow`.

## Forbidden In Bootstrap

- Auto-trading flows.
- Order entry or order routing flows.
- Nomination submission flows.
- ETRM replacement behavior.

