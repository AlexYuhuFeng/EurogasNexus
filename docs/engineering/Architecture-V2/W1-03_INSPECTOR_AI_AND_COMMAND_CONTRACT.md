# W1-03 — Inspector, Canonical AI Actions and Command Palette Contract

Status: **delivered contract (Wave 1)**. Authority: Architecture V2
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) sections 6, 7 and 9,
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) sections 4 and 6, and
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 28, 38-42.

Machine-readable form: `clients/web/src/app/experience/inspectorContract.ts`,
`aiActions.ts`, `actionGeography.ts`, `commandPalette.ts`.
Focused checks: `clients/web/tests/experienceArchitecture.test.ts`.

## 1. Canonical Inspector

Object detail belongs in one Inspector, not in a new top-level page per object kind
([W0-01_CLIENT_INVENTORY.md](W0-01_CLIENT_INVENTORY.md) section 3.3 records the current alternatives:
per-surface rails, drawers and master-detail panes).

Wave 1 delivers the contract as a pure state machine:

| Element | Contract |
|---|---|
| Subject | `{ kind, ref, label, originPage }` — an object kind from the vocabulary, a backend-owned stable reference, an already-localised label, and the page the selection came from. |
| Events | `open`, `close`, `back`, `reset` (`openInspector(subject)` builds the open event). |
| State | `{ subject, history }` with `INSPECTOR_HISTORY_LIMIT = 10`, so a long session cannot grow the stack without bound. |
| Gate | `canOpenInspector(kind, page)` — a workspace may only hand over the subject kinds its composition declares. |
| Empty ref | An `open` with an empty `ref` is refused and returns the previous state unchanged: an empty reference is not a subject. |

Rules:

1. A workspace MUST NOT open a subject kind it does not declare in its registry entry.
2. Opening detail MUST NOT create a top-level page or a route. `detailPlacement()` is `inspector`.
3. The Inspector presents what the caller already received from the backend under the current
   identity. It is not an authority boundary and MUST NOT fetch entitlement-restricted detail of
   its own.
4. The contract is deliberately not mounted yet. The Inspector region is declared `planned` in
   [W1-01](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md); moving surfaces onto it is Wave 9 work, and
   the reducer exists now so those surfaces cannot each invent their own selection model.

## 2. Action geography

The machine-readable form of `docs/ux/ACTION_GEOGRAPHY.md`, derived from what an action *does*:

| Consequence | Placement |
|---|---|
| `read` | `surface-local` |
| `compute` | `workspace-primary` |
| `persist` | `workspace-primary` |
| `export` | `workspace-secondary` |
| `lifecycle` | `object-overflow` |
| `destructive` | `object-overflow` |
| `utility` | `shell-utility` |

Rules:

1. A workspace SHALL declare at most one primary action, and only for `compute` or `persist`
   (`mayOccupyPrimarySlot`).
2. `lifecycle` and `destructive` actions MUST require a deliberate second step adjacent to the
   affected object (`requiresDeliberateStep`) and MUST NOT occupy the primary slot.
3. Placement is presentation only. It never grants authority, and hiding a control is not a
   permission check.

## 3. Canonical AI actions

Exactly five AI actions exist: **Ask, Explain, Compare, Challenge, Draft**. A surface MUST NOT
introduce an ad-hoc AI button outside this set.

| Action | Posture | Produces |
|---|---|---|
| `ask` | interpret-only | A sourced answer naming the data used and what it could not see. |
| `explain` | interpret-only | An explanation bound to the run, snapshot and assumptions it describes. |
| `compare` | interpret-only | A side-by-side reading naming the basis of comparison and missing inputs. |
| `challenge` | evidence-backed-review | A challenge record that stays evidence-linked and human-owned. |
| `draft` | evidence-backed-draft | A draft marked unverified until a named human accepts or edits it. |

Invariants (`AI_INVARIANTS`, asserted by the focused test):

- deterministic engines own calculations, optimisation and numeric truth;
- AI inherits the invoking user's authority and is re-authorised on every invocation;
- AI MUST NOT bypass entitlement, invent missing data, execute or nominate, or store hidden
  reasoning.

`aiActionIsAvailable(action, { activeContextComplete, evidenceRefCount })` withholds an action
without Active Context and without at least one evidence reference. Absence of evidence is a reason
to withhold the action, not a reason to let a model guess.

## 4. Command palette and keyboard model

The command set is derived, never hand-maintained:

- `navigationCommands()` — one command per primary work domain and one per technical page, built
  from `productNavigation`/`workspaceNavigation`, reusing the existing `nav.*` labels.
- `aiCommands()` — one command per canonical AI action.
- `utilityCommands()` — shell utilities that reuse the existing `topbar.*` labels, so the palette
  speaks the same vocabulary as the top bar instead of introducing synonyms.

Rules:

1. Command ids SHALL be unique and every command label SHALL exist in EN and zh-CN.
2. The palette shortcut is Ctrl+K / Cmd+K with no other modifier (`isPaletteShortcut`); Escape
   dismisses it (`isPaletteDismissKey`). The existing tab keyboard model in
   `clients/web/src/components/ui/tabKeyboard.ts` keeps its arrow/Home/End handling and is not
   overridden.
3. Ranking is label-prefix first, then substring, bounded by `DEFAULT_PALETTE_LIMIT` (8). An empty
   query returns the first window rather than the whole product surface.
4. A command declares what it does and where it belongs; capability questions stay with the
   backend. Wave 2 adds server-declared availability filtering
   ([06_IDENTITY_ACCESS_CONTROL_PLANE.md](06_IDENTITY_ACCESS_CONTROL_PLANE.md) section 9).

## 5. Verification

- Reducer behaviour: open, back, close, reset, empty-ref refusal, history bound, page gate.
- Action geography: one rule per consequence, primary-slot restriction, guarded consequences.
- AI actions: five canonical actions, invariant values, availability gating, EN/zh-CN labels.
- Palette: derived coverage of primaries and pages, AI command parity, unique ids, label parity,
  ranking and limit, shortcut and dismiss keys.

## 6. Compatibility and non-goals

- No rendering change: the palette, the Inspector panel and the AI actions are contracts, not
  mounted UI. No new page, route, dependency or backend call is introduced.
- No AI capability is created or widened. The contract only restricts how AI may be offered.
- Moving existing rails and drawers into the Inspector, and rendering the palette, are Wave 9
  migrations against these contracts.
