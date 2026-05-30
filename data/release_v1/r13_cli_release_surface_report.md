# R13: CLI Release Surface Report

**Milestone ID:** R13 | **Status:** COMPLETE | **Date:** 2026-05-29

## Evidence

- 25 CLI commands covering all route groups: health, reference network (5),
  sources (3), market (3), physical (3), LNG (2), storage (2), weather (3),
  contracts (2), glossary (2), workflows (3).
- All commands call SDK/API — no backend internal imports.
- JSON output via `_to_json()` for detail commands.
- Read-only by default (all commands are GET requests or research POST endpoints).

## Files

- `src/eurogas_nexus/cli/commands.py` — 25 commands
- `tests/cli/test_commands.py` (7 tests)

## Validation

- ruff: All checks passed
- pytest: 293 passed (was 286; +7)
- app: import ok, 52 routes

## Next: R14 Web Research Workspace

Internet required: yes (Node.js, npm, Vite, React package installation required).
Fallback if offline: create file structure, TypeScript interfaces, i18n/theme
resources, mocked API client, and gap report.
