# V1 R28 Product Hardening ExecPlan

## 1. Goal

Resolve verified cross-cutting delivery defects and complete the capacity-workspace
redesign: desktop development/runtime endpoint configuration, API error handling,
release-version consistency, obsolete API aliases, remaining `App.tsx` page
ownership, and trader-grade capacity semantics.

## 2. Non-goals

- No direct trade execution, order routing, or nomination submission.
- No client-side database or vendor connection.
- No new market-data dependency or live provider call.
- No inferred European pipeline geometry.

## 3. Product boundary

PostgreSQL remains the runtime source of truth. Web and desktop clients use the
backend `/api` surface. Desktop operators may configure a non-secret backend API
URL, but never a database URL or provider secret.

## 4. Files to create/modify

- Python, Web, and desktop package/version manifests
- `src/eurogas_nexus/api/app.py`
- `clients/web/src/api/client.ts`
- `clients/web/src/components/SettingsCenter.tsx`
- `clients/web/src/components/CapacityWorkspace.tsx`
- capacity-specific localization and styles
- extracted workspace components under `clients/web/src/components/`
- `clients/web/src/App.tsx`
- Tauri configuration
- API/path, client, release, and architecture contract tests
- current API/client/readme documentation

## 5. Dependency policy

Use the existing FastAPI, React, Zustand, TypeScript, Rust, and Tauri stack. Add
no dependency.

## 6. Data policy

- No runtime business data is added to the client.
- Capacity presentation distinguishes physical flow, firm technical capacity,
  booked capacity, and nominations. Missing or stale observations remain explicit.
- The backend API URL is a non-secret local preference.
- Remote backends require HTTPS; plain HTTP is accepted only for loopback
  development.
- Error messages must not echo submitted credentials.

## 7. API impact

Remove hidden `/api/v1/*` and `/v1/health` rewrites. `/api`, `/api/internal`, and
`/api/dev` remain authoritative. Add no business endpoint.

## 8. DB impact

Migration `0013_gie_lng_dtmi_energy` renames the incorrectly modeled ALSI DTMI
percentage field to the published energy-capacity field `dtmi_twh`. Local test
PostgreSQL is migrated explicitly; no migration runs during app import.

## 9. Tests

- Desktop dev command and `devUrl` use the same strict port.
- Manifest versions agree on `0.5.0`.
- API client rejects unsafe backend URLs and reports non-JSON responses clearly.
- Settings exposes backend API configuration without database/secret storage.
- Legacy API aliases return 404.
- Extracted workspaces remain API-owned and localized.
- Capacity utilization is computed only from physical flow divided by firm
  technical capacity; booked capacity is a separate commercial occupancy signal.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/unit
npm --prefix clients/web run build
npm --prefix clients/desktop run check
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- `tauri dev` points at the actual Vite port.
- A desktop operator can configure and test an API URL without editing the build.
- HTML/error responses never surface as raw JSON parse exceptions.
- Product versions are consistent across release manifests.
- The public API has one unversioned prefix.
- `App.tsx` orchestrates state and navigation instead of owning page markup.
- Capacity, access, tariff, storage, and LNG views are focused and do not mix
  incompatible capacity measures.
- Targeted validation, client builds, and release workflows pass.

## 12. Rollback notes

Revert the R28 commit and run the Alembic downgrade only on an explicitly
selected non-production runtime. The downgrade restores the legacy DTMI column
name but cannot restore incorrectly interpreted historical units.
