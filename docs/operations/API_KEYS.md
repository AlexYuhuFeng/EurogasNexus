# API Keys Runbook

## Model

Service credentials are owned by explicit USER/SERVICE principals. A key is
returned in plaintext exactly once. Only its digest (and optional keyed HMAC)
is stored.

## Admin actions

- `GET /api/access/api-keys` lists metadata (never secrets).
- `POST /api/access/api-keys` creates a key for a principal; copy the one-time
  `api_key` immediately.
- `POST /api/access/api-keys/{id}/revoke` revokes immediately.

## Verification

- Valid key passes `X-Eurogas-Identity: nexus_<key_id>_<secret>`.
- Revoked/expired key returns 403.
- Disabled owner makes every key fail immediately.

## Failure modes / recovery

Lost plaintext: rotate the key. Stolen key: revoke immediately, audit, and
issue a replacement. Never store the plaintext in files, localStorage, or
logs.

## Rollback

Revocation is not reversible by design; issue a new key.
