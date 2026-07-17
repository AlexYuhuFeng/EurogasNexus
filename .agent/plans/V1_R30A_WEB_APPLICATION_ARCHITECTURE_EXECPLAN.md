# V1 R30A Web Application Architecture ExecPlan

## 1. Goal

Refactor the active React application so the root component is a small
composition boundary rather than the owner of navigation, data refresh,
resource-pool derivation, source operations, glossary state, resource-term
editing, and every workspace render branch. Document the resulting structure
in English and Mandarin and enforce it with contract tests.

## 2. Non-goals

- No visual redesign or product-scope expansion.
- No backend, database, API, SDK, connector, or deployment behavior changes.
- No new client dependency or state-management framework.
- No migration of runtime data or simulated source records into the browser.

## 3. Product boundary

The Web and Tauri clients remain API consumers. PostgreSQL remains the runtime
source of truth. This refactor preserves the existing decision-support,
resource-pool, source, glossary, strategy, and resource-term workflows.

## 4. Files to create or modify

- Reduce `clients/web/src/App.tsx` to the application composition boundary.
- Add focused modules under `clients/web/src/app/hooks/`,
  `clients/web/src/app/model/`, `clients/web/src/app/shell/`, and
  `clients/web/src/app/workspaces/`.
- Export the API-store state contract required by application hooks.
- Update Web structure and release-surface contract tests to inspect the
  owning module instead of assuming every behavior lives in `App.tsx`.
- Add `docs/clients/WEB_APPLICATION_ARCHITECTURE-EN.md` and
  `docs/clients/WEB_APPLICATION_ARCHITECTURE-CN.md` and link them from the
  documentation indexes.

## 5. Dependency policy

Use the existing React, TypeScript, Zustand, i18next, Vite, MapLibre, and Tauri
stack. Add no dependency.

## 6. Data policy

No client fixtures, mock payloads, embedded market values, or local runtime
store are introduced. All business data continues to originate from the
backend API and its PostgreSQL runtime store.

## 7. API impact

None. Existing unversioned `/api` requests and response contracts remain
unchanged.

## 8. DB impact

None. No schema, migration, seed, or live database operation is required.

## 9. Tests

- TypeScript production build.
- Contract tests for module ownership, root-component size, API-only runtime
  data, navigation, source, glossary, resource-pool, and workspace wiring.
- Existing targeted Python validation suite.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
git diff --check
```

## 11. Acceptance criteria

- `App.tsx` is a small composition root and contains no workspace page markup.
- Navigation, runtime refresh, resource-term editing, source operations,
  glossary exploration, review analysis, and portfolio decision derivation
  have explicit owners.
- Workspace selection is centralized in one renderer.
- No browser-side business data is introduced.
- English and Mandarin architecture guides describe extension rules.
- Ruff, targeted tests, Web build, API import, and diff checks pass.

## 12. Rollback notes

The change is behavior-preserving and can be reverted as one commit. No API or
database rollback is needed.
