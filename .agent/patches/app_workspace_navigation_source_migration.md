# App Workspace Navigation Source Migration

## Goal

Move `clients/web/src/App.tsx` away from its local `WORKSPACE_PAGES` constant and use the shared navigation helpers from:

```text
clients/web/src/workspaceNavigation.ts
```

This patch must stay limited to the top navigation parsing logic. Do not rewrite the page body, workspace panels, data hooks, maps, or business workflows.

## Current shared source

`workspaceNavigation.ts` now exports:

```ts
workspaceGroups
workspacePageIds
isWorkspacePageId
coerceWorkspacePageId
WorkspacePageId
```

## Target App.tsx changes

### 1. Replace the existing WorkspaceTopBar type import

Current pattern:

```ts
import { WorkspaceTopBar, type WorkspacePageId } from "@/components/WorkspaceTopBar";
```

Target pattern:

```ts
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import { coerceWorkspacePageId, type WorkspacePageId } from "@/workspaceNavigation";
```

### 2. Remove the local `WORKSPACE_PAGES` constant

Delete the full local constant block that starts with:

```ts
const WORKSPACE_PAGES: WorkspacePageId[] = [
```

and ends with:

```ts
];
```

### 3. Replace `workspaceFromLocation()` implementation only

Current logic uses:

```ts
return WORKSPACE_PAGES.includes(requestedWorkspace as WorkspacePageId)
  ? requestedWorkspace as WorkspacePageId
  : "network";
```

Target logic:

```ts
return coerceWorkspacePageId(requestedWorkspace, "network");
```

Keep the `typeof window === "undefined"` guard.

## Acceptance checks

Run:

```bash
pytest -q tests/contract/test_workspace_navigation_contract.py
npm --prefix clients/web run build
```

## Non-goals

Do not change:

- workspace route ids such as `contracts` or `orders`;
- user-facing labels such as `Resource Terms` or `Market Positioning`;
- `WorkspaceTopBar` rendering;
- grouped navigation order;
- API calls, stores, backend routes, or data models.
