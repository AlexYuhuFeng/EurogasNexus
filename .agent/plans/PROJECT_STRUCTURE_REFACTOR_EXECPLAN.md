# Project Structure Refactor ExecPlan

Status: accepted for this worktree.

## Goal

Align Eurogas Nexus with common FastAPI/Python + React monorepo structure
practices:

- keep the backend in a `src/eurogas_nexus` package;
- keep process entrypoints thin under `apps/`;
- put pure domain logic under `src/eurogas_nexus/domain`;
- remove legacy/empty source placeholders;
- document the resulting ownership map.

## Non-goals

- No change to public API routes, SDK/CLI behavior, DB schema, or runtime
  semantics.
- No migration of the active SDK into `packages/python-sdk` (that remains a
  future packaging milestone).
- No UI refactor.
- No broad rename of client files.

## Changes

1. Move `src/eurogas_nexus/workflows/` to
   `src/eurogas_nexus/domain/research/`.
2. Update API imports and tests to use `eurogas_nexus.domain.research`.
3. Rename workflow model contract test to `test_research_models.py`.
4. Move pure research workflow tests from `tests/workflows/` to
   `tests/domain/research/`.
5. Remove empty `domain` placeholder packages that contained only
   `__init__.py`.
6. Update `PROJECT_DIRECTORY.md`, module ownership matrix, testing contract,
   and ontology gap-report status.

## Validation

- `ruff check .`
- `pytest -q tests/contract tests/domain/research tests/api tests/unit`
- `python scripts/ci/check_markdown_links.py`

## Acceptance criteria

- No `eurogas_nexus.workflows` imports remain.
- No empty source placeholder packages remain under `src/eurogas_nexus/domain`.
- All above validation commands pass.

## Rollback

Revert this branch. The refactor is file moves plus import/docs updates; no
database or API contract changes.
