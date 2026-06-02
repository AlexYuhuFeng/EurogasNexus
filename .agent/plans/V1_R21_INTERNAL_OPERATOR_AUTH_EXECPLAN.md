# V1 R21 Internal Operator Auth ExecPlan

## Goal

Harden `/api/internal/portfolio/import-observations` so screen-order and
portfolio PnL imports are not accepted unless the backend has an internal token
configured and the request supplies both a matching token and explicit operator
principal.

## Non-Goals

- Do not add company SSO/OIDC.
- Do not add browser, Web, Windows, SDK, or CLI use of the internal route.
- Do not add trade execution, order routing, trade capture, nomination, or
  auto-trading behavior.
- Do not call vendor APIs, LLM providers, or live infrastructure.
- Do not print, log, return, or commit the token value.

## Product Boundary

The internal route remains an operator/backend ingestion path only. Release
clients continue to consume read-only `/api/v1/portfolio/*` routes.

## Files To Create Or Modify

- Create `src/eurogas_nexus/security/internal_api.py`
  - import-safe static internal token helper;
  - `EUROGAS_NEXUS_INTERNAL_API_TOKEN` env policy;
  - safe `InternalApiAuthError` without secret values.
- Modify `src/eurogas_nexus/api/routes/internal/portfolio_import.py`
  - require `X-Eurogas-Internal-Token`;
  - require `X-Eurogas-Principal`;
  - fail before DB access when auth fails.
- Add `tests/security/test_internal_api_auth.py`.
- Update `tests/api/test_internal_market_positioning_import.py`.
- Update docs:
  - `docs/operations/MARKET_POSITIONING_IMPORTS-EN.md`
  - `docs/operations/MARKET_POSITIONING_IMPORTS-CN.md`
  - `docs/clients/CLIENT_API_CONTRACT.md`
  - `PROJECT_DIRECTORY.md`
  - `README.md`
  - `docs/architecture/CURRENT_PAUSE_POINT.md`

## Dependency Policy

Use only Python standard library modules: `hmac`, `os`, and `dataclasses`.

## Data Policy

Use synthetic test tokens only. Do not add real secrets or `.env` values.

## API Impact

Internal profile route now requires:

```text
X-Eurogas-Internal-Token: <operator-managed-token>
X-Eurogas-Principal: <operator-or-job-id>
```

Configured env:

```text
EUROGAS_NEXUS_INTERNAL_API_TOKEN
```

Failure codes:

- `internal_api_token_not_configured` -> 503
- `internal_api_token_missing` -> 401
- `internal_api_token_invalid` -> 403
- `internal_principal_missing` -> 401

## DB Impact

No schema change. Failed auth returns before DB access and before observation
rows can be written.

## Tests

- Unit tests prove configuration detection, token verification, and safe error
  messages.
- API tests prove:
  - success requires configured env token, matching request token, and principal;
  - missing token config fails closed;
  - missing/wrong token fails closed;
  - missing principal fails closed;
  - release profile still does not expose the route.

## Validation Commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
rg "90f8185523dad1fbc69ed05bb80d3a0d" .
```

## Acceptance Criteria

- App import remains DB-free and token-free.
- Internal route fails before DB access if token/principal validation fails.
- Internal route still imports when env token, request token, principal, DB URL,
  and entitlement rows are present.
- Release profile route remains unavailable.
- No real token is committed or printed.

## Rollback Notes

Reverting this checkpoint restores the previous entitlement-only internal route
behavior. No DB migration rollback is required.
