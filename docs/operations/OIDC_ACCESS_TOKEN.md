# OIDC Access Token Runbook

Chinese companion: [OIDC_ACCESS_TOKEN-CN.md](OIDC_ACCESS_TOKEN-CN.md)

## Purpose

R32A adds a reviewed OIDC **access-token verification** path without adding a
JWT/OIDC SDK dependency. It is a machine-to-machine bearer validation flow, not
a browser login flow. No redirect, PKCE, refresh token, or session cookie is
implemented.

## Configuration

```text
EUROGAS_NEXUS_OIDC_ISSUER=https://idp.example.com/realms/nexus
EUROGAS_NEXUS_OIDC_CLIENT_ID=eurogas-nexus
EUROGAS_NEXUS_OIDC_AUDIENCE=eurogas-api
EUROGAS_NEXUS_OIDC_ROLE_CLAIM=roles
EUROGAS_NEXUS_OIDC_SCOPE_CLAIM=entitlements
EUROGAS_NEXUS_OIDC_ALLOW_HTTP=false
```

- `ISSUER` must be HTTPS. `ALLOW_HTTP=true` is for a reviewed development/test
  issuer only.
- `CLIENT_ID` is required. `AUDIENCE` defaults to the client id.
- Discovery (`/.well-known/openid-configuration`) and JWKS are fetched lazily
  at first request and cached for 300 seconds. Importing the API makes no
  network call.

## Client request

Release clients still send the deployment token:

```http
X-Eurogas-Api-Key: <public-api-token>
X-Eurogas-Oidc-Access-Token: <RS256 access token>
```

`X-Eurogas-Identity` (local DB key) takes precedence when both identity headers
are present.

## Verification rules

- Algorithm must be RS256 and `kid` must be present.
- JWKS key is matched by `kid` and verified with SHA-256/PKCS#1 v1.5.
- `iss`, `aud`, `exp`, `nbf`, and non-empty `sub` are enforced with 60 seconds
  leeway.
- Unrecognized role claims map to VIEWER (least privilege). Recognized aliases:
  admin/administrator → ADMIN; operator/ops/operations → OPERATOR;
  analyst/trader/research → ANALYST; viewer/read → VIEWER.
- `entitlements`/`data_scopes` claim values become commercial data scopes;
  unknown families still fail closed at the entitlement layer.

## Operations

- Invalid tokens are audited best-effort as
  `identity.authentication.denied` without storing the token.
- Private-network/VPN-only server posture is unchanged until a real security
  acceptance review.

## Non-goals

- No login redirect, PKCE, refresh tokens, sessions, or SAML.
- No identity-provider calls in import-time code or automated tests.
