# Codex Cleanup Targets

This is the single checklist for frontend workspace-navigation cleanup. Keep all edits narrow and local. Do not rewrite `App.tsx` wholesale.

## Non-goals

Do not change route ids, user-facing labels, API calls, stores, backend routes, data models, map rendering, or page bodies.

## Target 1: App workspace source migration

File: `clients/web/src/App.tsx`

Reference: `.agent/patches/app_workspace_navigation_source_migration.md`

Codex should clear the local `WORKSPACE_PAGES` constant and make `workspaceFromLocation()` use the shared helpers from `clients/web/src/workspaceNavigation.ts`:

- `coerceWorkspacePageId`
- `DEFAULT_WORKSPACE_PAGE_ID`
- `WorkspacePageId`

Final expectation:

- `App.tsx` imports workspace navigation helpers from `@/workspaceNavigation`.
- `App.tsx` no longer declares local `WORKSPACE_PAGES`.
- URL fallback uses `DEFAULT_WORKSPACE_PAGE_ID`.

## Target 2: App-owned legacy workspace menu state

File: `clients/web/src/App.tsx`

Reference: `.agent/patches/remove_legacy_workspace_menu.md`

Codex should clear the App-owned workspace menu state because grouped menu state now lives inside `WorkspaceTopBar`.

Final expectation:

- App no longer owns a workspace menu open/closed state variable.
- App no longer toggles the workspace menu.
- TopBar remains the only owner of grouped menu state.

## Target 3: Legacy props passed into WorkspaceTopBar

File: `clients/web/src/App.tsx`

Codex should clear the two obsolete menu-control props from the `WorkspaceTopBar` call.

Final expectation:

- TopBar still receives active workspace, search, status, language, theme, and callbacks.
- TopBar no longer receives App-owned menu state or a menu-toggle callback.

## Target 4: Old flat App workspace menu block

File: `clients/web/src/App.tsx`

Codex should clear the old flat workspace menu block rendered by App.

Final expectation:

- App no longer renders a flat `workspace-menu` nav.
- `clients/web/src/components/WorkspaceTopBar.tsx` remains responsible for the grouped menu.

## Target 5: Temporary TopBar compatibility index

File: `clients/web/src/components/WorkspaceTopBar.tsx`

After Targets 2 and 3 are complete, Codex should clear the temporary compatibility index signature from `WorkspaceTopBarProps`.

Final expectation:

- `WorkspaceTopBarProps` exposes only explicit supported props.
- The contract test asserts there is no compatibility index signature in the props interface.

## Target 6: Transitional App parity test

File: `tests/contract/test_workspace_navigation_contract.py`

After Target 1 is complete, Codex should update the App parity test.

Final expectation:

- The test asserts `App.tsx` imports from `@/workspaceNavigation`.
- The test asserts `App.tsx` no longer declares local `WORKSPACE_PAGES`.
- The test no longer depends on reading page ids from App.

## Validation

Run:

```bash
pytest -q tests/contract/test_workspace_navigation_contract.py
npm --prefix clients/web run build
pytest -q tests
```
