# SSO/OIDC Runbook

## Purpose

Interactive enterprise login uses Authorization Code + PKCE. The backend
exchanges the code, validates issuer/audience/signature/nonce, maps
issuer+subject to a local principal, and creates a backend session.

## Configuration

```text
EUROGAS_NEXUS_OIDC_ISSUER=https://idp.example.com/realms/nexus
EUROGAS_NEXUS_OIDC_CLIENT_ID=eurogas-nexus
EUROGAS_NEXUS_OIDC_AUDIENCE=eurogas-api
EUROGAS_NEXUS_OIDC_CLIENT_SECRET=   # only if token endpoint requires it
EUROGAS_NEXUS_OIDC_PROVISIONING_MODE=preprovisioned
EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS=   # required for approved_domain JIT
EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP={"nexus-analysts":"ANALYST"}
EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP={"nexus-analysts":["EEX"]}
EUROGAS_NEXUS_OIDC_ALLOW_HTTP=false
```

The provider must register the backend callback URI (default
`/api/auth/oidc/callback`) as a public-client redirect URI.

## Verification

1. `GET /api/auth/status` shows `oidc_configured=true`.
2. Open `/api/auth/oidc/login`; the provider authorization page appears.
3. After login, `GET /api/me` returns principal, roles, permissions, scopes
   and a session CSRF token.
4. Admin sees the SSO profile under System → Access & Identity → SSO.

## Failure modes

- `oidc_not_configured`: issuer/client missing.
- `oidc_discovery_unavailable`: discovery/JWKS endpoint unreachable.
- `oidc_state_invalid`/`oidc_pkce_invalid`: replayed callback or mismatch.
- `oidc_nonce_invalid`: token reuse/wrong token type.
- `external_identity_not_provisioned`: correct by linking issuer+subject in
  `identity_external_ids` or by enabling approved-domain JIT.

## Safe recovery

- Correct configuration and restart; discovery/JWKS cache expires in 300s.
- Never set `ALLOW_HTTP=true` in production.
- Pre-provision identities in the database; do not grant Admin/analyst by
  default on first login.

## Rollback

Set `EUROGAS_NEXUS_OIDC_ISSUER=""` and restart to disable SSO; existing API
keys and the internal administration path remain available.

## Emergency access policy

No permanent backdoor exists. A deployment-managed local ADMIN service
principal with a strong API key is the supported break-glass path and must be
created and audited explicitly.
