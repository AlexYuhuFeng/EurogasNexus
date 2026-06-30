# V1 R22 Docs And Client Cockpit Alignment ExecPlan

## Goal

Bring the repository guidance, release docs, Mandarin docs, and Web client
structure into line with the current product state: a PostgreSQL-backed,
map-first gas trader intelligence cockpit with active Web and Windows surfaces.

## Non-goals

- Do not add trade execution, order entry, order routing, nomination, booking,
  approval, settlement, or ETRM behavior.
- Do not add live external provider calls from tests or client code.
- Do not add new frontend runtime dependencies.
- Do not implement a full contract persistence workflow in this batch.

## Product Boundary

Eurogas Nexus remains decision support only. UI language must use terms such as
signal, option, candidate, allocation, review, warning, and source evidence.
It must not imply official recommendations or executable actions.

## Files To Create Or Modify

- Update documentation alignment tests under `tests/contract/`.
- Repair corrupted Mandarin docs under `docs/clients/` and `docs/operations/`.
- Update stale architecture/client/release docs that still treat Web/Windows as
  future-only.
- Extract focused Web client components from `clients/web/src/App.tsx` without
  changing the API boundary.
- Add a compact warning/evidence drilldown to the Network decision rail.

## Dependency Policy

Use the existing Python, React, TypeScript, Vite, MapLibre, i18next, and
Zustand stack only. No new package dependencies.

## Data Policy

Runtime data continues to flow only through backend `/api` routes. Missing
runtime data must remain visible as blocked, partial, unavailable, or
credential-missing state. Do not add browser-side sample runtime data.

## API Impact

No new API routes in this batch. The Web client continues to use the existing
`/api` client.

## DB Impact

No migrations or schema changes.

## Tests

- Add contract tests for docs encoding/current-state alignment.
- Add contract tests for Web client component boundaries.
- Run targeted contract tests.
- Run `npm --prefix clients/web run build`.
- Run API import and live runtime status checks.
- Browser-smoke Network and Data Sources with console checks.

## Acceptance Criteria

- Mandarin docs selected by the tests contain valid, readable Chinese and no
  private-use/replacement characters.
- Current-state docs no longer direct agents back to backend Milestone 2 or
  describe Web/Windows runtime code as future-only.
- Web source center/topbar code is split into focused components.
- Network cockpit shows a compact warning/evidence stack for trader review.
- Targeted contract tests and Web build pass.

## Rollback Notes

All changes are source/docs-only. Revert this batch by restoring modified docs,
tests, and Web client files; no database rollback is needed.
