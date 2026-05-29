# Current Pause Point

## Status

Holistic live runtime testing has been performed against the current worktree.
The project is stronger than the previous pause point, but it is **not yet an
official V1 release**.

Current implementation status:

- Backend/API/SDK/CLI: locally validated against live Docker PostgreSQL.
- Web client: builds successfully and has a MapLibre map workspace backed by
  `/api/v1`.
- Windows client: still not implemented; documentation only.
- Live connectors and LLM provider access: still mocked/gated.

Read the full evidence report:

```text
data/release_v1/holistic_real_test_report.md
```

## Runtime Evidence

Validated on 2026-05-29:

```text
ruff check .
pytest -q
npm run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
python scripts/ops/validate_v1_runtime_db.py --json
```

Results:

```text
Ruff: passed
Python tests: 312 passed
Web build: passed, with Vite chunk-size warning
App import: app import ok, 53 routes
Runtime DB: revision 0003_r3_reference_network, missing_tables=0
```

Live walkthrough:

```text
API: 39 GET + 8 POST workflow calls passed
SDK/CLI: health, runtime-db, nodes, route options, HDD/CDD, route cost,
         netback, feasibility passed
Web proxy: /api/v1/reference-network/nodes and /api/v1/runtime/db passed
```

## Work Completed Since Previous Pause

- Fixed pytest collection by enabling importlib import mode.
- Converted `eurogas_nexus.db.repositories` into a package.
- Added DB-backed reference-network API reads with DB-free import safety.
- Added synthetic V1 PostgreSQL reference-network seed script.
- Added `/api/v1/runtime/db`.
- Added SDK and CLI runtime DB status calls.
- Added actual CLI entrypoint.
- Replaced the Web map placeholder with a MapLibre network map.
- Added Web runtime/source/route/market panels.
- Added `package-lock.json` by installing declared Web dependencies.
- Ignored generated Web `node_modules` and `dist`.

## Remaining Official Release Blockers

1. Windows client must be implemented and packaged with Tauri.
2. Browser-level Web interaction testing is still needed.
3. Web bundle should be code-split before production packaging.
4. Live ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, and weather connectors remain
   mocked/offline.
5. LLM analysis route remains a placeholder and needs gated provider integration.
6. Most non-reference data routes still serve synthetic fixtures rather than
   DB-backed canonical tables.
7. Auth, audit persistence, entitlement routes, and export-governance runtime
   enforcement remain partial.

## Commit Rule

Do not create an official-release commit yet. The current work can be committed
only as a **holistic validation and release-hardening checkpoint**, not as an
official V1 release.

## Next Prompt

```text
Read AGENTS.md, CLAUDE_CODE_START_HERE.md,
docs/architecture/CURRENT_PAUSE_POINT.md, and
data/release_v1/holistic_real_test_report.md.

Continue Eurogas Nexus V1 release hardening from the current worktree.
Start with the first official-release blocker:
implement the Windows client shell with Tauri, wrapping the existing Web
workspace, using /api/v1 only and storing only non-sensitive UI preferences.
After that, add browser-level Web interaction tests and code-split the Web
bundle. Keep live vendor and LLM calls gated until credentials, entitlement,
internet policy, and operator validation are explicitly available.

Do not claim official V1 release readiness until every blocker in
data/release_v1/holistic_real_test_report.md is complete or explicitly accepted
as a release limitation by the user.
```
