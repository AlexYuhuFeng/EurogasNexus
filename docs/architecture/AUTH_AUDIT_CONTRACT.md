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

- Production identity-provider calls at import time.
- Permission bypasses hidden inside route handlers.

## CR-10 Additions

- Interactive enterprise OIDC login (Authorization Code + PKCE), provider
  discovery/JWKS caching, issuer+subject external identity mapping,
  pre-provisioning by default and optional approved-domain JIT with explicit
  group maps.
- Backend-managed sessions (`user_sessions`) with hashed tokens, logout,
  disable-driven revocation, and CSRF/origin protection for cookie
  authentication.
- Fine-grained permission expansion (`security/authorization.py`) with
  VIEWER/ANALYST/REVIEWER/OPERATOR/ADMIN and public Access & Identity APIs.
- API keys remain first-class service credentials with scopes/created_by and
  keyed HMAC hashing when the deployment secret is configured.
- Audit events remain append-only and now carry permission/correlation/client
  type and safe before/after summaries.

## R32 Additions

- `identity_principals` and `identity_api_keys` are PostgreSQL-owned; key
  plaintext is returned once and only its SHA-256 hash is persisted.
- Release-profile roles are enforced from the permission registry:
  VIEWER for PUBLIC/READ, ANALYST for GOVERNED, OPERATOR for OPERATOR.
- R32A OIDC access-token verification is allowed only through
  `security/oidc.py`; discovery/JWKS calls are lazy request-time HTTPS calls
  and never occur at import time. Company SSO/OIDC interactive login flows
  were previously forbidden; CR-10 delivers Authorization Code + PKCE for the
  reviewed single-organization deployment model. SAML remains forbidden.
- Audit rows are append-only, export is internal-only and bounded, and
  retention pruning is dry-run by default with a minimum 30-day window.

## Milestone 9 Additions

- Contract tests validate that bootstrap-forbidden auth behaviors remain explicitly documented.
- Validation commands include `tests/security` to keep auth/audit boundary checks active.
