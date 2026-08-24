# Identity, Authorization, And Audit Governance Runbook

Chinese companion: [IDENTITY_AUDIT_GOVERNANCE-CN.md](IDENTITY_AUDIT_GOVERNANCE-CN.md)

## Supported identity model

R32 supports local PostgreSQL identities. There is no company SSO/OIDC in this
increment and no OIDC dependency was introduced.

| Item | Behavior |
|---|---|
| Principal | USER or SERVICE row in `identity_principals` |
| Roles | VIEWER, ANALYST, OPERATOR, ADMIN |
| Credential | Hashed bearer API key in `identity_api_keys` |
| Client header | `X-Eurogas-Identity: nexus_<key_id>_<secret>` |
| Legacy deployment | `X-Eurogas-Api-Key` without identity header remains an OPERATOR service principal |
| Private-network posture | Unchanged until security acceptance |

## Internal administration

All routes below require `X-Eurogas-Internal-Token` and a valid
`X-Eurogas-Principal` header.

```text
GET    /api/internal/identities
POST   /api/internal/identities
POST   /api/internal/identities/{principal_id}/keys
POST   /api/internal/identities/{principal_id}/keys/{key_id}/rotate
POST   /api/internal/identities/{principal_id}/keys/{key_id}/revoke
POST   /api/internal/identities/{principal_id}/disable
GET    /api/internal/audit/events
POST   /api/internal/audit/prune
```

- `POST .../keys` returns the bearer once. Copy it before leaving the page.
- `GET /api/internal/identities` never returns hashes or plaintext keys.
- Rotating a key revokes the old key before issuing the replacement.
- Disabling a principal stops every key immediately.

## Role authorization

| Permission category | Minimum role |
|---|---|
| PUBLIC / READ | VIEWER |
| GOVERNED | ANALYST |
| OPERATOR | OPERATOR |

ADMIN satisfies every role. Legacy deployment-token callers keep OPERATOR
compatibility. The registry is tested by `tests/security/test_permissions_registry.py`
and enforced in the release profile by `route_permission.py`.

## Commercial-data scopes

`identity_principals.data_scopes` contains source-family grants. Public
baseline families (`operator-input`, `ENTSOG`, `GIE`, `ECB`, `Weather`) are
available to every active identity. Commercial families require an explicit
grant:

```json
["EEX", "ICE_OCM", "Trayport"]
```

`*` grants all families for operator/admin service identities. Unknown
commercial families fail closed. Market observation and quote responses filter
rows to the authenticated identity's granted families.

## Audit retention and export

- Default retention: 365 days; allowed window 30-3650 days.
- Prune is dry-run by default:

```bash
python scripts/ops/prune_audit_events.py --retention-days 365
python scripts/ops/prune_audit_events.py --retention-days 365 --commit
```

- `POST /api/internal/audit/prune` accepts `retention_days` and `dry_run`.
- `GET /api/internal/audit/events` exports bounded, non-secret audit rows and
  records an `audit.export` event.
- Identity lifecycle actions always append audit events.

## Remaining R32A scope

- Company SSO/OIDC/SAML, browser sessions, and password lifecycle.
- Security acceptance and removal of the private-network/VPN-only posture.
