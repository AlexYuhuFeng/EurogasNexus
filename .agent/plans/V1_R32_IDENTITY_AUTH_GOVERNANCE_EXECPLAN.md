# R32: Local Identity, Authorization, Entitlement, Audit Governance ExecPlan

## 1. Goal

Deliver the first production-usable multi-user identity layer without adding
company SSO/OIDC dependencies. PostgreSQL becomes the identity and API-key
store, roles authorize public and operator surfaces, commercial-data
entitlement is enforced per identity, and audit retention/export controls are
operational. The server remains private-network/VPN-only until security
acceptance.

## 2. Non-goals

- No company SSO/OIDC/SAML dependency or runtime identity-provider call in
  this increment; the integration point is documented and deferred to a
  separately reviewed R32A after an ExecPlan dependency review.
- No password-based login, browser sessions, refresh tokens, or password
  reset.
- No removal of the private-network/VPN-only server posture.
- No client (Web/desktop) identity screens; SDK/CLI header plumbing is
  backend-contract only.
- No trade execution, nomination, or approval behavior.

## 3. Product boundary

- Public release profile: existing deployment token still proves the
  installed client/deployment; a new `X-Eurogas-Identity` bearer key proves a
  DB-stored USER or SERVICE principal.
- Roles: `VIEWER`, `ANALYST`, `OPERATOR`, `ADMIN`.
  - PUBLIC/READ routes: VIEWER+.
  - GOVERNED routes: ANALYST+.
  - OPERATOR routes: OPERATOR+.
  - Internal identity/audit administration: internal token + valid principal
    header + OPERATOR+.
- Principal `data_scopes` gate commercial source families; unknown commercial
  families always fail closed.
- Identity keys are returned once in plaintext; only SHA-256 hashes are stored.
- Audit events are append-only; retention pruning is operator-controlled and
  audited.

## 4. Files to create/modify

Create:

- `src/eurogas_nexus/db/models/identity.py`
- `alembic/versions/0022_identity_api_keys.py`
- `src/eurogas_nexus/db/repositories/identity.py`
- `src/eurogas_nexus/security/identity.py`
- `src/eurogas_nexus/api/dependencies/identity.py`
- `src/eurogas_nexus/api/routes/internal/identity_admin.py`
- `src/eurogas_nexus/application/audit_retention.py`
- `scripts/ops/prune_audit_events.py`
- `tests/security/test_identity_model.py`
- `tests/security/test_identity_admin_api.py`
- `tests/security/test_identity_row_entitlement.py`
- `tests/security/test_audit_retention.py`
- `docs/operations/IDENTITY_AUDIT_GOVERNANCE.md` and `-CN.md`

Modify:

- `src/eurogas_nexus/db/models/__init__.py`
- `src/eurogas_nexus/db/registry.py`
- `src/eurogas_nexus/api/app.py`
- `src/eurogas_nexus/api/routes/internal/router.py`
- `src/eurogas_nexus/api/dependencies/route_permission.py`
- `src/eurogas_nexus/api/dependencies/entitlement.py`
- `src/eurogas_nexus/security/permissions.py`
- `src/eurogas_nexus/api/routes/public/market.py`
- `src/eurogas_nexus/sdk/_http.py`
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE*.md`
- `docs/architecture/CURRENT_PAUSE_POINT*.md`
- `docs/architecture/ACTOR_IDENTITY_MODEL*.md`
- `docs/contracts/13_AUTH_AUDIT_CONTRACT.md`
- `tests/contract/test_architecture_alignment.py`

## 5. Dependency policy

Python standard library + existing FastAPI/Pydantic/SQLAlchemy/cryptography
stack only. No OIDC/JWT/passlib/Argon2 dependency. API-key hashing uses
`hashlib.sha256` with constant-time comparison; secrets use `secrets`.

## 6. Data policy

- Identity rows are test-only synthetic data in automated tests
  (`test_fixture:not_customer_data`).
- Key plaintext is never logged, returned twice, or persisted.
- Data scopes are stored as uppercase source-family strings or `*`.
- Audit export excludes provider credentials, encrypted payloads, DB DSNs, and
  request headers. It is restricted to internal token + operator principal.

## 7. API impact

Additive internal-only paths:

```text
GET    /api/internal/identities
POST   /api/internal/identities
POST   /api/internal/identities/{principal_id}/keys
POST   /api/internal/identities/{principal_id}/keys/{key_id}/revoke
POST   /api/internal/identities/{principal_id}/disable
GET    /api/internal/audit/events
POST   /api/internal/audit/prune
```

Internal paths are profile-gated and do not alter the pinned public 92-path
surface.

## 8. DB impact

Migration `0022_identity_api_keys` adds two tables:

- `identity_principals`
- `identity_api_keys`

Required-table registry grows from 40 to 42. No existing table columns
change.

## 9. Tests

- Identity key generation/authentication: hash-only storage, revocation,
  expiry, disabled principal, constant-time failures, role precedence.
- Internal identity admin API: token+principal gating, create/list, key
  plaintext-once, rotate/revoke/disable, audit rows written.
- Role authorization in release profile: VIEWER blocked on governed/operator
  routes; ANALYST allowed governed, blocked operator; OPERATOR allowed.
- Row entitlement: scoped identity allowed only declared families; unknown
  commercial family denied; legacy deployment token retains compatibility.
- Audit retention: dry-run, bounded retention, script parse, endpoint export
  excludes secrets.
- Registry/migration/docs alignment.

## 10. Validation commands

```powershell
ruff check src tests scripts apps alembic
pytest -q tests/security tests/api tests/contract tests/integration tests/unit tests/sdk
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
```

## 11. Acceptance criteria

1. A DB-stored principal authenticates with a bearer API key and receives a
   typed role and data scopes.
2. Role requirements are enforced on public OPERATOR and GOVERNED routes.
3. Unknown commercial source families fail closed for scoped identities.
4. Key plaintext appears only in the create/rotate response and is never
   stored or re-read.
5. Identity changes and audit export/prune actions append audit events.
6. Audit retention policy is executable with dry-run and documented defaults.
7. Private-network/VPN-only posture is explicitly retained until security
   acceptance.
8. All validation commands pass (except documented sandbox subprocess limits).

## 12. Rollback notes

Revert this increment and run `alembic downgrade 0021`. Public route behavior
for deployments that do not send `X-Eurogas-Identity` is compatibility
preserved; internal identity/audit endpoints disappear on rollback.
