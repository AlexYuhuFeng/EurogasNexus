# ASVS 5.0 Control Mapping — CR-10

Status legend: IMPLEMENTED / PARTIAL / EXTERNAL_ACCEPTANCE_REQUIRED /
NOT_APPLICABLE. A status is never claimed merely because a test exists.

## V1 Architecture, Design and Threat Modeling

| Control area | Status | Evidence |
|---|---|---|
| Explicit single-organization trust boundary | IMPLEMENTED | `docs/security/ENTERPRISE_IDENTITY_AUTHORIZATION_SPEC.md`; no tenant abstractions |
| No execution/order/nomination capability | IMPLEMENTED | product-boundary tests; no such permission verbs exist |
| Threat model kept in repository | PARTIAL | design/anti-pattern sections; external threat review remains required |

## V2 Authentication

| Control area | Status | Evidence |
|---|---|---|
| OIDC Authorization Code + PKCE for interactive login | IMPLEMENTED | `application/enterprise_auth.py`, `api/routes/public/auth.py` |
| Provider-neutral issuer/client discovery | IMPLEMENTED | `security/oidc.py` |
| Local principal + external identity link by issuer+subject | IMPLEMENTED | `identity_external_ids`, repository tests |
| Disabled/locked principals denied | IMPLEMENTED | session/key authentication checks owner status |
| No local password system | NOT_APPLICABLE | enterprise SSO is primary; no password table |
| API-key lifecycle (create/rotate/revoke/expire) | IMPLEMENTED | `identity_api_keys`, access API |
| API-key storage strength | PARTIAL | SHA-256 legacy compatibility; keyed HMAC for new keys when `EUROGAS_NEXUS_SECRET_KEY` is set |

## V3 Session Management

| Control area | Status | Evidence |
|---|---|---|
| Server-side sessions with hashed token | IMPLEMENTED | `user_sessions`; token digest only |
| HttpOnly/Secure/SameSite cookie | IMPLEMENTED | login callback `Set-Cookie` (Secure on https) |
| Logout and session revocation | IMPLEMENTED | `/api/auth/logout`, disable revokes sessions |
| Idle/absolute expiry | IMPLEMENTED | touch/absolute expiry in repository |
| CSRF/origin protection for cookie auth | IMPLEMENTED | `OriginCsrfGuardMiddleware` + `/api/me` CSRF token |

## V4 Access Control

| Control area | Status | Evidence |
|---|---|---|
| Centralized RBAC permission expansion | IMPLEMENTED | `security/authorization.py` |
| Coarse route permission registry for every public path | IMPLEMENTED | `security/permissions.py` + tests |
| Data scopes separate from roles | IMPLEMENTED | `identity_principals.data_scopes`; CR-09 filters |
| Derived-result entitlement enforcement | IMPLEMENTED | CR-09 route/strategy/shadow/report filters |
| Unknown role/permission/scope fail closed | IMPLEMENTED | authorization and entitlement tests |
| Object-level ownership model | NOT_APPLICABLE | research objects are organization-visible by design |

## V5 Input Validation and API Security

| Control area | Status | Evidence |
|---|---|---|
| Pydantic request validation | IMPLEMENTED | all public routes |
| Reject forged OIDC issuer/audience/algorithm | IMPLEMENTED | OIDC tests |
| Rate limiting on auth/admin endpoints | PARTIAL | documented as pending deployment middleware; not yet instrumented |

## V6 Cryptography and Key Handling

| Control area | Status | Evidence |
|---|---|---|
| Cryptographically secure random keys/sessions/states | IMPLEMENTED | `secrets` |
| OIDC RS256/JWKS signature validation | IMPLEMENTED | `security/oidc.py` + offline RSA tests |
| Provider credentials Fernet-encrypted | IMPLEMENTED | `security/credentials.py` |
| Secrets never returned/logged | IMPLEMENTED | API responses/audit redaction tests |
| Key rotation support | IMPLEMENTED | internal + access API |

## V7 Logging and Error Handling

| Control area | Status | Evidence |
|---|---|---|
| Structured audit events, append-only APIs | IMPLEMENTED | `audit_events`, no mutation endpoints |
| Login/identity/strategy/dataops/decision audit hooks | IMPLEMENTED | CR-10 + CR-09 hooks |
| Secret/token/payload redaction | IMPLEMENTED | audit/minimization policy and tests |
| Raw provider/LLM payload never audited | IMPLEMENTED | existing policy |

## V8 Data Protection

| Control area | Status | Evidence |
|---|---|---|
| Row/derived-result commercial entitlement | IMPLEMENTED | CR-09/CR-10 tests |
| Licensed-data boundary | IMPLEMENTED | CR-09 typed policies |
| No refresh/access tokens in browser storage | IMPLEMENTED | backend cookie session; desktop in-memory only |
| Historical run immutability | IMPLEMENTED | unchanged CR-04/CR-06 behavior |

## V9 Communication Security

| Control area | Status | Evidence |
|---|---|---|
| HTTPS issuer enforcement | IMPLEMENTED | `EUROGAS_NEXUS_OIDC_ALLOW_HTTP` fail closed |
| Explicit CORS origins with credentials | IMPLEMENTED | `api/app.py` |
| CSP without `unsafe-eval` | IMPLEMENTED | `tauri.conf.json` |
| Deep-link hijack resistance | PARTIAL | loopback single-use callback; external acceptance pending |

## V10 Malicious Code / V14 Configuration

| Control area | Status | Evidence |
|---|---|---|
| No client secrets in Web/desktop binaries | IMPLEMENTED | public OIDC client; token endpoint optional secret stays server-side |
| Tauri least-privilege capabilities | IMPLEMENTED | `capabilities/default.json` (`core:default` only) |
| Dependency pinning/audit in CI | IMPLEMENTED | existing CI |
| External penetration/security acceptance | EXTERNAL_ACCEPTANCE_REQUIRED | unchanged `SECURITY_ACCEPTANCE_EVIDENCE.md` |
