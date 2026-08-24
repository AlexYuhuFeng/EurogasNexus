# Explicit deployment_posture Switch ExecPlan

## 1. Goal

Add an explicit, import-safe `deployment_posture` configuration switch:
`private_network_preview` (default) and `security_accepted`. The latter is
effective only when an operator-supplied security-acceptance evidence file
also exists.

## 2. Non-goals

- Do not remove the current private-network/VPN-only deployment posture.
- Do not alter PowerShell deployment preflight behavior.
- Do not expose the switch as a client or public API value.
- Do not perform the external security acceptance itself.

## 3. Product boundary

`src/eurogas_nexus/core/config.py` owns the setting. A helper returns whether a
public-network deployment may be considered allowed; callers (future
deployment/middleware work) consume the helper rather than reading the env var
directly.

## 4. Files to create/modify

Create:

- `tests/unit/test_deployment_posture.py`

Modify:

- `src/eurogas_nexus/core/config.py`
- `.env.example`
- `docs/deployment/DEPLOYMENT_ROLES-EN.md`
- `docs/deployment/DEPLOYMENT_ROLES-CN.md`
- `docs/architecture/CURRENT_PAUSE_POINT*.md`
- `docs/release/RELEASE_READINESS.md`
- `docs/release/SECURITY_ACCEPTANCE_EVIDENCE.md`
- `scripts/security/run_security_acceptance.py`

## 5. Dependency policy

No new dependency.

## 6. Data policy

No database or business data change. Evidence path is a local operator file
path; the helper checks existence only.

## 7. API impact

None. Public path count remains 84.

## 8. DB impact

None.

## 9. Tests

- Default posture is private-network preview.
- `security_accepted` without evidence file is rejected.
- `security_accepted` with an existing evidence file is allowed.
- Invalid env values fail validation.
- Security acceptance script checks the switch default.

## 10. Validation commands

```powershell
ruff check src tests scripts apps alembic
pytest -q tests/unit/test_deployment_posture.py tests/security/test_security_acceptance.py
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"
```

## 11. Acceptance criteria

1. Env var `EUROGAS_NEXUS_DEPLOYMENT_POSTURE` is parsed into Settings.
2. `public_network_deployment_allowed()` is false unless posture is
   `security_accepted` and evidence path points to a file.
3. Existing private-network-only behavior and tests remain unchanged.

## 12. Rollback notes

Remove the config fields/helper and tests; no migration or API change.
