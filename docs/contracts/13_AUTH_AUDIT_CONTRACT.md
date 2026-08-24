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

## R32 Additions

- `identity_principals` and `identity_api_keys` are PostgreSQL-owned; key
  plaintext is returned once and only its SHA-256 hash is persisted.
- Release-profile roles are enforced from the permission registry:
  VIEWER for PUBLIC/READ, ANALYST for GOVERNED, OPERATOR for OPERATOR.
- R32A OIDC access-token verification is allowed only through
  `security/oidc.py`; discovery/JWKS calls are lazy request-time HTTPS calls
  and never occur at import time. Interactive OIDC login flows and SAML remain
  forbidden until a separate reviewed ExecPlan.
- Audit rows are append-only, export is internal-only and bounded, and
  retention pruning is dry-run by default with a minimum 30-day window.

## Milestone 9 Additions

- Contract tests validate that bootstrap-forbidden auth behaviors remain explicitly documented.
- Validation commands include `tests/security` to keep auth/audit boundary checks active.
