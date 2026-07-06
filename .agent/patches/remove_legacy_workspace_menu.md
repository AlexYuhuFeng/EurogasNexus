# Remove Legacy App-Owned Workspace Menu

Apply this local patch after the grouped menu has been moved into `WorkspaceTopBar`.

Target file:

```text
clients/web/src/App.tsx
```

Remove these fragments:

```tsx
const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
```

```tsx
workspaceMenuOpen={workspaceMenuOpen}
onWorkspaceMenuToggle={() => setWorkspaceMenuOpen((current) => !current)}
```

Remove the old flat menu block that starts with:

```tsx
{workspaceMenuOpen && (
  <nav className="workspace-menu" aria-label={t("topbar.workspace_menu")}>
```

and ends with the matching `)}` before `<main className="app-main">`.

Validation:

```bash
pytest -q tests/contract/test_workspace_navigation_contract.py
npm --prefix clients/web run build
```
