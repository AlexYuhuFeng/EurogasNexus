# R32A: OIDC Access-Token Authentication ExecPlan

## 1. Goal

Add a reviewed, dependency-free OIDC access-token verification path to the
release API while retaining local PostgreSQL identity keys. An access token
from a configured issuer is verified (RS256 signature, issuer, audience,
expiry, subject) and mapped to a role/data-scope principal without adding a
JWT/OIDC SDK dependency.

## 2. Non-goals

- No OIDC login flow, browser redirect, PKCE, refresh token, or session cookie.
- No SAML.
- No live identity-provider calls in import-time code or automated tests.
- No automatic removal of the private-network/VPN-only posture; that remains
  gated on a real security acceptance review.

## 3. Product boundary

Release clients may send either a DB identity key in `X-Eurogas-Identity` or
an OIDC access token in `X-Eurogas-Oidc-Access-Token`. The static public API
token remains the deployment-transport credential and is still required.
Issuer discovery and JWKS retrieval happen lazily at request time, with a
bounded TTL cache and no import-time network I/O.

## 4. Files to create/modify

Create:

- `src/eurogas_nexus/security/oidc.py`
- `tests/security/test_oidc.py`
- `tests/security/test_oidc_api.py`
- `docs/operations/OIDC_ACCESS_TOKEN.md` and `-CN.md`

Modify:

- `src/eurogas_nexus/api/dependencies/identity.py`
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE*.md`
- `docs/architecture/CURRENT_PAUSE_POINT*.md`
- `docs/architecture/ACTOR_IDENTITY_MODEL*.md`
- `docs/contracts/13_AUTH_AUDIT_CONTRACT.md`
- `.agent/plans/V1_R32_IDENTITY_AUTH_GOVERNANCE_EXECPLAN.md` (status note)

## 5. Dependency policy

No new Python dependency. Uses stdlib `json`/`base64`/`hmac`-adjacent helpers,
`httpx` (already allowed) for discovery/JWKS, and `cryptography` (already
allowed) for RS256 signature verification.

## 6. Data policy

- No OIDC access token is logged, stored, or returned.
- Test signing keys are generated in memory by `cryptography`; no external
  provider is contacted.
- Claims map to roles/data scopes fail-closed: unrecognized role claims yield
  VIEWER (least privilege) and unknown commercial scopes are denied at the
  entitlement layer.

## 7. API impact

No new public path. Release behavior is additive: a new optional header
`X-Eurogas-Oidc-Access-Token`. Public pinned path count remains 92.

## 8. DB impact

None. OIDC principals are transient and are not persisted.

## 9. Tests

- Token parse, RS256 signature verification, JWKS kid selection.
- Rejections: malformed token, wrong key, expired, not-yet-valid, wrong
  issuer/audience, missing sub, non-RS256.
- Role mapping from `roles`, `realm_access.roles`, and `scope` claims.
- API integration: viewer/analyst/operator OIDC identities on release routes
  and fail-closed unconfigured/missing-issuer errors.
- Import-safety: importing the API still does not import DB or call a network.

## 10. Validation commands

```powershell
ruff check src tests scripts apps alembic
pytest -q tests/security tests/contract/test_db_foundation.py tests/contract/test_import_boundaries.py
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
```

## 11. Acceptance criteria

1. A valid OIDC RS256 access token authenticates and maps sub/roles/scopes.
2. Signature, issuer, audience, and temporal claims are all verified.
3. Discovery/JWKS are fetched lazily and cached; import-time network is zero.
4. Existing DB identity keys and legacy public-token behavior are unchanged.
5. Private-network/VPN-only posture is retained until security acceptance.

## 12. Rollback notes

Remove the OIDC header branch in `api/dependencies/identity.py` and delete
`security/oidc.py` plus its docs/tests. No migration or public path change.
