# API Keys Runbook

## Model

Service credentials are owned by explicit USER/SERVICE principals. A key is
returned in plaintext exactly once. Only its digest (and optional keyed HMAC)
is stored.

## Two credentials, two headers: deployment gateway key vs identity key

A deployment may require two independent credentials on the same request:

- the **deployment (gateway) key** is the static `EUROGAS_NEXUS_PUBLIC_API_TOKEN`
  checked by the public-API gate before any route runs. It is accepted as
  `X-Eurogas-Api-Key: <token>`, `Authorization: Bearer <token>`, or
  `?api_key=<token>` (intended for SSE, where `EventSource` cannot set headers;
  use headers for ordinary requests to avoid putting secrets in URLs);
- the **per-principal identity key** is a `nexus_<key_id>_<secret>` bearer
  resolved against the identity store. It is accepted only as
  `X-Eurogas-Identity: nexus_<key_id>_<secret>`.

When both are required, send each in its own header:

```text
X-Eurogas-Api-Key: <deployment token>
X-Eurogas-Identity: nexus_<key_id>_<secret>
```

Do **not** put the identity key in `Authorization: Bearer` or `?api_key=`. The
deployment gate prioritises Bearer over the dedicated deployment header and
uses the query value only when neither supplies a token. It verifies against the
deployment token, so an identity key sent there is refused with 403
`public_api_token_invalid` before identity resolution. That is a caller header
error — not an expired, revoked or unprovisioned identity key, and not a reason
to change the deployment configuration.

## Admin actions

- `GET /api/access/api-keys` lists metadata (never secrets).
- `POST /api/access/api-keys` creates a key for a principal; copy the one-time
  `api_key` immediately.
- `POST /api/access/api-keys/{id}/revoke` revokes immediately.

## Verification

- A valid identity key presented as `X-Eurogas-Identity: nexus_<key_id>_<secret>`
  authenticates and resolves the principal's roles and data scopes.
- A malformed bearer (not `nexus_<key_id>_<secret>`) returns 401
  `identity_bearer_missing`. A revoked or expired key returns 403
  (`identity_key_revoked` / `identity_key_expired`); an unknown key returns 403
  `identity_key_invalid`; a disabled owner makes every key fail with 403
  `identity_principal_disabled`.
- A verified deployment token alone resolves the legacy compatibility service
  principal (OPERATOR rank, single trust domain); it carries no identity or
  access administration.
- A valid identity whose role is below the route's required floor returns 403
  `identity_role_forbidden`; an identity holding administration alone is
  refused commercial data with 403 `commercial_access_not_granted`. Both are
  correct refusals, not key defects.
- Missing deployment credentials return 401 `public_api_token_missing` at the
  public gate; an unconfigured required deployment token returns 503
  `public_api_token_not_configured`. If identity resolution is reached with no
  accepted identity or compatibility credential, it returns 401
  `authentication_required`. Identity-key authentication with no configured
  identity store returns 503 `identity_store_not_configured`; an unavailable
  configured store returns 503 `identity_store_unavailable`.

## Failure modes / recovery

Lost plaintext: rotate the key. Stolen key: revoke immediately, audit, and
issue a replacement. Never store the plaintext in files, localStorage, or
logs.

A 403 seen in a probe: first re-check which header carried which credential
(the two-header form above) before suspecting provisioning or expiry.

## Do not weaken authentication to clear a 403

Do not disable or bypass the deployment token, do not move an identity key into
the bearer/query channel, and do not widen a principal's roles to make a
refusal disappear. The deployment gate fails closed with 503 when its token is
unconfigured, and every refusal above is deliberate.

## Rollback

Revocation is not reversible by design; issue a new key.
