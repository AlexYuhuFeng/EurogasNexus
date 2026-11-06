# Components: one control per meaning

Status: adopted 2026-11-06 (#27). Related: `docs/product/ADAPTIVE_CLIENT.md`, `docs/product/UX_REFERENCE.md`.

The same meaning looks and behaves the same on every page. Different meanings may look
different. Shared components and design-system tokens are the single source of truth. A page
does not add its own variant of an existing control.

| Meaning | Use | Not |
|---|---|---|
| The page's commit (save, run, issue) | `WorkspaceHeader` `primaryAction` slot: one per page, styled `button-primary` | A second primary button in a panel |
| Secondary action | A plain `<button>` | `secondary-button` is an alias kept for existing pages; do not add new aliases |
| Inline or navigational action | `link-button` | `text-action`, `research-text-button` (retired) |
| Destructive action | Quiet `danger-quiet` until confirmed; the confirm is `button.danger` | A red button that acts on first click |
| Switch between sub-views | `WorkspaceTabs` (URL-backed through `useUrlView`) | Pills or segmented buttons for navigation |
| Choose one value of a parameter | A segmented control (`aria-pressed` buttons) or a `<select>` | Tabs |
| Status of a record | `StatusBadge` with the matching variant | Free-text colour spans |
| Nothing to show | `EmptyState`: one reason and one next step | Rows or cards of "n/a", empty bars, repeated "Unavailable" badges |
| Long explanation that is not always needed | `<details>` with a short summary (`scope-fold`) | A permanently open paragraph |
| Object detail | The Inspector or the page's detail panel; a full-screen sheet with Back on a phone | A new page per object |

Sizes come from the control tokens (`--ds-control-sm`, `--ds-control`, `--ds-control-lg`). With a
coarse pointer, every button, link button, input and select is at least 44 px tall, and
checkboxes and radios are 20 px. Focus is always visible. `tests/componentVocabulary.test.ts`
fails if a retired variant comes back.
