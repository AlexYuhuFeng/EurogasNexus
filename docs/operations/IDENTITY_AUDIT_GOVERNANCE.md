# Identity, Authorization, And Audit Governance Runbook

Chinese companion: [IDENTITY_AUDIT_GOVERNANCE-CN.md](IDENTITY_AUDIT_GOVERNANCE-CN.md)

## Supported identity model

CR-10 extends R32 with interactive enterprise SSO (Authorization Code + PKCE),
backend sessions, REVIEWER role, and fine-grained permissions. Local
PostgreSQL identities and service API keys remain supported.

| Item | Behavior |
|---|---|
| Principal | USER or SERVICE row in `identity_principals` |
| Roles | VIEWER, REVIEWER, ANALYST, OPERATOR, ADMIN (overlapping; a principal may hold several) |
| Credential | Hashed bearer API key in `identity_api_keys` |
| Client header | `X-Eurogas-Identity: nexus_<key_id>_<secret>` |
| Legacy deployment | `X-Eurogas-Api-Key` without identity header remains an OPERATOR service principal |
| Private-network posture | Unchanged until security acceptance |

## Unauthenticated is a real state

`GET /api/me` returns 401 `unauthenticated` when the request presented no
credential at all (no `X-Eurogas-Identity`, no `X-Eurogas-Oidc-Access-Token`,
no `eurogas_session` cookie). The legacy OPERATOR service principal is still
attached for SDK/CLI compatibility when the release profile verified the static
deployment API token, and for any validated identity key, OIDC token, or
backend session, so existing integrations are unaffected.

## Development credential login (development profile only)

`POST /api/dev/auth/login` exists **only** in the development route profile; the
internal and release profiles do not register the route, so it cannot be reached
there. `GET /api/auth/status` reports `dev_login` as true only when the route is
mounted *and* the credential pair is configured.

```text
EUROGAS_NEXUS_DEV_LOGIN_USERNAME=<existing ACTIVE principal name or email>
EUROGAS_NEXUS_DEV_LOGIN_PASSWORD=<development-only secret>
```

- Unset credentials: 503 `dev_login_disabled` (fail-closed).
- Wrong username or password: 401 `invalid_credentials` (constant-time compare).
- Credentials match but no ACTIVE local principal has that username/email:
  403 `identity_not_provisioned`.
- Success: the same backend `eurogas_session` cookie as the OIDC flow, plus an
  `authenticated: true` capability envelope.

This endpoint never creates, approves, or elevates a principal, and never grants
a role or data scope of its own. Never set these variables in a trial or release
deployment.

## Registration never auto-approves

Just-in-time provisioning (`EUROGAS_NEXUS_OIDC_PROVISIONING_MODE=approved_domain`)
registers an unknown approved-domain identity with status `PENDING`; the first
SSO login is rejected with `identity_pending_approval` instead of receiving a
session. An administrator must activate the principal (`status = "ACTIVE"`)
before that identity can authenticate. Pre-provisioned identities that are
already `ACTIVE` are unaffected. Registration is therefore never approval: no
first login auto-grants terminal access.

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

ADMIN satisfies every role *floor* (highest rank), and legacy deployment-token
callers keep OPERATOR compatibility. Rank is not commercial access: since
Architecture V2 (ADR-0016) a platform-administration identity holds no
commercial-data permission, and a commercial path is refused with 403
`commercial_access_not_granted` unless the principal also holds a commercial
role (for example ANALYST). The registry is tested by
`tests/security/test_permissions_registry.py` and enforced in the release
profile by `route_permission.py`; the commercial boundary is enforced by
`api/dependencies/commercial_access.py` and tested by
`tests/security/test_platform_admin_commercial_boundary.py`.

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

## Remaining scope

- SAML and a production password lifecycle remain out of scope. The
  development credential login stores no password in the database and is not a
  substitute for SSO.
- Live enterprise IdP acceptance is deployment-specific and not claimed from
  local cryptographic fixtures.
- Security acceptance and removal of the private-network/VPN-only posture.
