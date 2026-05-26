# Auth Audit Contract

## Purpose

`src/eurogas_nexus/auth_runtime` owns future runtime authorization checks.
`src/eurogas_nexus/audit` owns future audit event models and sinks.

## Bootstrap State

Only package boundaries exist.

## Rules

- Authorization decisions must be explicit and testable.
- Audit events must record actor, action, resource, decision, and timestamp once
  implemented.
- Audit sinks must be dependency-injected.
- Importing the API must not contact identity providers.

## Forbidden In Bootstrap

- Company SSO/OIDC.
- Production identity-provider calls.
- Permission bypasses hidden inside route handlers.

