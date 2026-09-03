# Auth Audit Contract

## Purpose

Runtime authorization and audit are governed by the active `security/`,
`governance/`, and `application/` packages rather than empty placeholder
packages. If future dedicated adapter modules are needed, they are created
with their first implementation under `security/`, `governance/`, or
`application/`.

## Current state

- `src/eurogas_nexus/security/` owns identity principals, API keys, OIDC
  verification, permissions, provider keys, and public/internal API auth.
- `src/eurogas_nexus/governance/` owns entitlement and audit policy.
- `src/eurogas_nexus/application/` owns audit services, retention, and audit
  workflow orchestration.

## Rules

- Authorization decisions must be explicit and testable.
- Audit events must record actor, action, resource, decision, and timestamp.
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
