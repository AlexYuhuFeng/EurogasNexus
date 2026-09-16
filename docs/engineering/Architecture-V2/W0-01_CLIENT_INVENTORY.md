# W0-01 Client Inventory (React routes, workspaces, panels, navigation, client API dependencies)

Status: Wave 0 evidence artifact. Documentation only. Not an acceptance of Wave 0.

- Task: W0-01 (DeepSeek worker brief, `.automation/runtime/tasks/W0-01.md`).
- Repair task: W0-01-R1 (Astra integration review; brief `.automation/runtime/tasks/W0-01-R1.md`).
  W0-01 was REWORK_REQUIRED, not accepted; this repair corrects the evidence in this file only.
- Baseline HEAD in the original brief: `d42e71b330c4df97c97c2d61b52f9e18f4d4c39b`.
- Original inspection HEAD: `d42e71b330c4df97c97c2d61b52f9e18f4d4c39b`.
- Repair inspection HEAD: `dd1abe143cec7b6bd9a1c90090b210b59b5fe0ba` (`git rev-parse HEAD`,
  2026-09-14; the review baseline given in the repair brief).
  `git diff --name-only d42e71b dd1abe1` lists only `.automation/*` files, so every `clients/...`
  line reference below is unchanged between the original inspection and this repair.
- Scope: `clients/web` React workspace and the `clients/desktop` Tauri host seams that the web client talks to. Backend route semantics were cross-checked only against the repository's own pinned API surface test; no backend file was modified. No code, schema, API, dependency, configuration, security, permission, entitlement, release or UI behaviour was changed by the original task or by this repair.

Authority read for this task: `AGENTS.md`, `docs/engineering/Architecture-V2/CODEX_ENTRYPOINT.md`,
`AUTONOMOUS_EXECUTION_POLICY.md`, `02_ARCHITECTURE_CONSTITUTION.md`,
`04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`, `11_CURRENT_TO_TARGET_GAP_MATRIX.md`,
`12_MIGRATION_ROADMAP.md`, `18_DEEPSEEK_WORKER_PROTOCOL.md`,
`docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` (read-only),
`README.md`, `PROJECT_DIRECTORY.md`, `docs/README.md`,
`docs/architecture/ARCHITECTURE_DECISION_RECORD.md` (Decision 14),
`docs/engineering/RFC-0001-UI-CONVERGENCE.md`,
`docs/clients/WEB_APPLICATION_ARCHITECTURE-EN.md`.

Repository truth is used for current behaviour; the V2 pack is used only for target direction.
No ADR is changed, accepted or superseded here.

### Path convention used below

Full repository-relative paths are used wherever a reference could be mistaken for another file.
Short forms appear only for basenames that are unique under `clients/web/src` (verified by script;
47 distinct short forms in this revision, 0 ambiguous):

- `AppShell.tsx` = `clients/web/src/app/shell/AppShell.tsx`;
  `WorkspaceRenderer.tsx` = `clients/web/src/app/workspaces/WorkspaceRenderer.tsx`;
  `productNavigation.ts` = `clients/web/src/app/navigation/productNavigation.ts`;
  `workspaceNavigation.ts` = `clients/web/src/workspaceNavigation.ts`;
  `useWorkspaceNavigation.ts` = `clients/web/src/app/hooks/useWorkspaceNavigation.ts`;
  `viewPreference.ts` = `clients/web/src/app/context/viewPreference.ts`;
  `commercialWorkflowModel.ts` = `clients/web/src/app/model/commercialWorkflowModel.ts`;
  `usePortfolioDecisionModel.ts` = `clients/web/src/app/model/usePortfolioDecisionModel.ts`.
- Bare component names such as `MarketCockpit.tsx`, `PortfolioWorkspace.tsx`, `DecisionWorkspace.tsx`,
  `ScenarioWorkspace.tsx`, `ReviewWorkspace.tsx`, `MarketPositioningWorkspace.tsx`,
  `SourceCenter.tsx`, `RuntimeWorkspace.tsx`, `AccessCenter.tsx`, `ResearchDataWorkspace.tsx`,
  `AgentsWorkspace.tsx`, `WorkspaceTopBar.tsx`, `AlertCenter.tsx`, `SignInScreen.tsx`,
  `ManualWorkspace.tsx` = `clients/web/src/components/<name>` (strategy components:
  `clients/web/src/components/strategy/<name>`).
- `api/client.ts` = `clients/web/src/api/client.ts`;
  `stores/api.ts` = `clients/web/src/stores/api.ts`;
  `stores/authGate.ts` = `clients/web/src/stores/authGate.ts`;
  `stores/workspaceLoading.ts` = `clients/web/src/stores/workspaceLoading.ts`.
- The form `clients/web/src/hooks/useIdentitySignal.ts` used in the first revision of this file was a
  path error (that directory does not exist); the hook is
  `clients/web/src/app/hooks/useIdentitySignal.ts` (§1.2).

## 0. Authority conflict recorded (not resolved here)

- `docs/architecture/ARCHITECTURE_DECISION_RECORD.md:289-320` (Decision 14) makes
  RFC-0001 + the Professional UI Constitution the binding visual/interaction contract, with
  implementation acceptance explicitly still open ("pre-refactor workflow inventory and coverage
  remain incomplete; its gate stays open").
- `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md:39-53` defines the target
  Canonical Experience Shell (Global Context / Navigation / Primary Workspace / Inspector /
  Activity / Notifications / Command Palette / Copilot); `:161-187` defines work modes and the
  "composition only, not authority" rule; `:97-108` defines the Inspector rule.
- `docs/engineering/Architecture-V2/11_CURRENT_TO_TARGET_GAP_MATRIX.md` marks, on line 26,
  "Navigation: functional workspace based" as **REFACTOR** ("Shell + patterns + work-mode
  composition"); on line 28 "Inspector/detail: inconsistent" as ADD; and on line 24
  "Market/Portfolio/Strategy pages: feature-centric" as REFACTOR. Tests that pin today's
  page-id/route contract (see §7) protect that current contract; they are not evidence that the
  present navigation composition is the accepted V2 target.
- The orchestrator checkpoint (`docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`) records this
  conflict as auto-reconciled under `AUTONOMOUS_EXECUTION_POLICY.md`, with a superseding ADR to
  preserve decision history. This inventory neither supersedes nor implements Decision 14; it
  only records what exists today.

## 1. Entry, shell and host boundary (current behaviour)

| Layer | File | Behaviour | Reference |
|---|---|---|---|
| Composition root | `clients/web/src/App.tsx` | Imports `useAppController()` and renders `<AppShell controller={controller} />`; 8 lines, no routing logic | `clients/web/src/App.tsx:1-8` |
| Controller | `clients/web/src/app/hooks/useAppController.ts` | Builds one controller object: i18n, api store, theme, navigation, trader/selection context, cockpit controls, contract editor, portfolio model, review, glossary, sources | `clients/web/src/app/hooks/useAppController.ts:15-79` |
| Identity signal | `clients/web/src/app/hooks/useIdentitySignal.ts` | Publishes non-secret identity resolution to `window.__EUROGAS_IDENTITY__` and the `eurogas:identity` event; calls `notifyDesktopClientReady()` once the state is resolved | `clients/web/src/app/hooks/useIdentitySignal.ts:10-40` |
| Shell | `clients/web/src/app/shell/AppShell.tsx` | Three sequential gates (see §1.1), then top bar, endpoint-failure banner, `<main id="workspace-primary-content">` | `clients/web/src/app/shell/AppShell.tsx:31-226` |
| Page dispatch | `clients/web/src/app/workspaces/WorkspaceRenderer.tsx` | Maps the active primary workspace / page id to a component | `clients/web/src/app/workspaces/WorkspaceRenderer.tsx:58-239` |

### 1.1 Visible gates in the shell

1. Release compatibility gate — a blocking `ReleaseCompatibility` state renders a full-page
   blocker before anything else (`clients/web/src/app/shell/AppShell.tsx:31-58`).
2. Identity gate — `api.authState !== "authenticated"` renders `SignInScreen`; the workspace,
   panels and every protected read stay unmounted. The comment states the URL never decides what
   mounts (`clients/web/src/app/shell/AppShell.tsx:60-82`).
3. Partial-load banner — rendered only when endpoint failures exist; shows translated labels,
   failure codes and a bounded list plus a retry control (`clients/web/src/app/shell/AppShell.tsx:86-164`).

### 1.2 Host seams (Tauri stays a host; no business logic in Rust)

| Seam | Web side | Host side | Purpose |
|---|---|---|---|
| Desktop deployment config | `hydrateApiBaseUrlFromDesktopDeployment()` `clients/web/src/api/client.ts:153-164` | `read_deployment_config` `clients/desktop/src-tauri/src/main.rs:50-63` | Reads backend base URL from a desktop deployment file |
| Client readiness | `notifyDesktopClientReady()` `clients/web/src/api/client.ts:172-189` | `notify_client_ready` `clients/desktop/src-tauri/src/main.rs:71-93` | Reveals the main window and closes the splashscreen after identity resolves (bounded fallback) |
| Session data wipe | `clearDesktopSessionData()` `clients/web/src/api/client.ts:191-206` | `clear_client_session_data` `clients/desktop/src-tauri/src/main.rs:95-106` | Drops WebView cookies/caches/local storage on sign-out |
| Desktop SSO | `startDesktopOidcLogin` / `desktopOidcToken` client calls + `invoke("start_loopback_auth")` / `invoke("open_browser_login_and_wait")` `clients/web/src/stores/api.ts:1031-1062` | `start_loopback_auth`, `open_browser_login_and_wait` `clients/desktop/src-tauri/src/main.rs:108-186` | Loopback OIDC with PKCE in the desktop shell |
| Identity signal | `useIdentitySignal(authState, principalId)` `clients/web/src/app/hooks/useIdentitySignal.ts:28-40`; payload/keys in `clients/web/src/stores/authGate.ts:224-250` | Rust reads `window.__EUROGAS_IDENTITY__` or the `eurogas:identity` event | The host owns window visibility; the web app owns resolution |

Registered Tauri commands are exactly the five above
(`clients/desktop/src-tauri/src/main.rs:210-220`, `invoke_handler` list at `:214-219`). `clients/desktop/src-tauri/tauri.conf.json:6-11`
confirms the desktop bundle packages `../../web/dist` and builds with `npm --prefix ../web run build`.

### 1.3 Base URL and credential handling (current behaviour, recorded not judged)

- Browser default base `"/api"`, desktop default `http://127.0.0.1:8000/api`, overridable by
  `VITE_EUROGAS_API_BASE_URL` or a stored value (`clients/web/src/api/client.ts:3-13, 100-150`).
- Client-held credentials: optional API token in `localStorage` (`eurogas.settings.api_token`),
  operator principal (`eurogas.settings.operator_principal`), in-memory desktop session token and
  CSRF token; sent as `Authorization: Bearer`, `X-Eurogas-Principal`, `X-Eurogas-CSRF`
  (`clients/web/src/api/client.ts:6-8, 15-26, 44-86`). Requests use `credentials: "include"`
  (`clients/web/src/api/client.ts:92-98`).
- Sign-out clears the stored token/principal and asks the desktop host to wipe session data, but
  deliberately keeps non-secret preferences (`clients/web/src/api/client.ts:63-76`,
  `clients/web/src/stores/api.ts:1065-1096`).

## 2. Route / workspace / navigation registry

### 2.1 Technical page ids (16) — `clients/web/src/workspaceNavigation.ts`

`WorkspacePageId` union (`:1-16`) and `workspacePageIds` array (`:19-35`) declare, in order:
`network`, `capacity`, `market`, `scenario`, `contracts`, `strategy`, `review`, `orders`,
`sources`, `glossary`, `runtime`, `settings`, `manual`, `access`, `research`, `agents`.

- Default page: `DEFAULT_WORKSPACE_PAGE_ID = "network"` (`:38`).
- Guard: `isWorkspacePageId` (`:40-42`), coercion with fallback (`:44-49`).
- URL task helper: `workspaceTaskSearch(search, page, task)` sets `workspace=` and writes
  `task=` only for `scenario`/`review` or an explicit task (`:51-58`).

### 2.2 Primary (product) navigation — `clients/web/src/app/navigation/productNavigation.ts`

| Primary id | Label key | Child pages | Default page | Reference |
|---|---|---|---|---|
| `market` | `nav.primary.market` | `network`, `market`, `capacity` | `network` | `:18-25` |
| `portfolio` | `nav.primary.portfolio` | `contracts`, `orders` | `contracts` | `:26-32` |
| `strategy` | `nav.primary.strategy` | `strategy` | `strategy` | `:33-39` |
| `decision` | `nav.primary.decision` | `scenario`, `review` | `scenario` | `:40-46` |
| `system` | `nav.primary.system` | `sources`, `runtime`, `research`, `agents`, `settings`, `manual`, `glossary`, `access` | `sources` | `:47-53` |

Helpers: `primaryWorkspaceForPage` (throws for an unmapped page) `:66-72`,
`primaryWorkspaceForId` `:74-79`, `isPrimaryWorkspaceId` `:81-84`,
`defaultWorkspacePageForPrimary` `:87-93`. `PrimaryWorkspaceId`/`PrimaryWorkspace`
interfaces at `:3-16`.

Every child appears exactly once across the five primaries; this is asserted by
`tests/contract/test_workspace_navigation_contract.py` and `clients/web/tests/productNavigation.test.ts`.

### 2.3 URL contract and history semantics

- Workspace is read from `?workspace=`; unknown values fall back to `network`
  (`clients/web/src/app/hooks/useWorkspaceNavigation.ts:38-50`).
- Resolution order, read from `workspaceFromLocation()` itself rather than from its intent comment
  (`clients/web/src/app/hooks/useWorkspaceNavigation.ts:38-50`):
  1. an explicit `?workspace=` that names a page id wins outright (this is what keeps the legacy
     deep links `?workspace=network` and `?workspace=capacity` working); an unknown value falls
     back to `network` (`clients/web/src/workspaceNavigation.ts:44-49`);
  2. only when `?workspace=` is absent: a market `?task=` (`overview|curves|network|capacity`) or
     the authenticated principal's persisted market view (`curves|network`) selects the `market`
     shell page (`marketViewLandingPageCandidate`,
     `clients/web/src/app/context/viewPreference.ts:63-71`);
  3. otherwise the declared default `DEFAULT_WORKSPACE_PAGE_ID = "network"`.
  Two consequences are recorded here because they decide route semantics later in this document:
  while `?workspace=` is present the persisted preference is not consulted at all, and a `?task=`
  on its own never selects a workspace page.
  Inside the `market` shell the task is then resolved by `resolveMarketViewTask`
  (`clients/web/src/app/context/viewPreference.ts:202-215`): URL `?task=`, then
  `?workspace=network`/`capacity`, then the persisted view, then `curves`. The
  `?workspace=network` branch of that resolver is unreachable in practice because the shell
  intercepts `network` before the renderer mounts (§2.4); `marketTaskFromLocation`
  (`clients/web/src/app/model/marketCockpitModel.ts:24-31`) applies the workspace branches
  *before* `?task=` and is **not** used by the runtime UI - only by tests
  (`clients/web/tests/marketCockpit.test.ts:31-37`, `clients/web/tests/workspaceHeader.test.ts:29-33`),
  and `clients/web/tests/marketViewSeparation.test.ts:60` asserts the cockpit must not call it.
- Deep links are only honoured while the identity gate is open; after sign-out/session loss the
  protected query keys `workspace, task, route, resource, run, strategy, version, gasDay, product,
  hub` are stripped from the entry URL (`clients/web/src/app/hooks/useWorkspaceNavigation.ts:66-80`,
  `clients/web/src/stores/authGate.ts:176-222`).
- `openWorkspace(page, task?)` pushes `{workspace}` history state and bumps `locationRevision`;
  `openPrimaryWorkspace` opens the primary's default page, except Market which honours the
  persisted view (`clients/web/src/app/hooks/useWorkspaceNavigation.ts:93-115`).
- `popstate` re-reads the URL (`clients/web/src/app/hooks/useWorkspaceNavigation.ts:82-90`).

Query keys used across the app (all client-owned, no router library): `workspace`, `task`,
`route`, `resource`, `run`, `strategy`, `version`, `gasDay`, `product`, `hub`
(trader context: `clients/web/src/app/context/contextUrl.ts`; selection: same file).
Selection and trader context also persist a non-secret copy
(`clients/web/src/app/context/contextPersistence.ts:1-60`, key `eurogas.traderContext.v1`).

### 2.4 Registered page id → component dispatch (renderer + shell)

| Page id | Primary | Rendering component | Mount site |
|---|---|---|---|
| `network` | market | `NetworkWorkspace` **mounted directly by the shell** (map-first standalone page) | `clients/web/src/app/shell/AppShell.tsx:166-224` |
| `market` | market | `MarketCockpit` | `clients/web/src/app/workspaces/WorkspaceRenderer.tsx:92-94` |
| `capacity` | market | `MarketCockpit` (task `capacity` → `CapacityWorkspace`) | `WorkspaceRenderer.tsx:92-94`; `clients/web/src/components/MarketCockpit.tsx:355-365` |
| `contracts` | portfolio | `PortfolioWorkspace` | `WorkspaceRenderer.tsx:96-98` |
| `orders` | portfolio | `PortfolioWorkspace`, whose task is resolved from `?task=` only; `?workspace=orders` alone renders the **overview** task, and `MarketPositioningWorkspace` mounts only with `?task=exposure` | `WorkspaceRenderer.tsx:96-98`; `clients/web/src/components/PortfolioWorkspace.tsx:150-165, 212-220`; `clients/web/src/app/model/commercialWorkflowModel.ts:14-17` |
| `strategy` | strategy | `StrategyLabWorkspace` (design/backtest/compare/shadow) | `WorkspaceRenderer.tsx:104-119`; `clients/web/src/components/strategy/StrategyLabWorkspace.tsx:37-56, 70-101` |
| `scenario` | decision | `DecisionWorkspace` (task `scenario` → `ScenarioWorkspace`) | `WorkspaceRenderer.tsx:100-102`; `clients/web/src/components/DecisionWorkspace.tsx:158-176` |
| `review` | decision | `DecisionWorkspace` (task `review` → `ReviewWorkspace`) | `clients/web/src/components/DecisionWorkspace.tsx:178-199` |
| `sources` | system | `SourceCenter` | `WorkspaceRenderer.tsx:121-158` |
| `glossary` | system | `GlossaryWiki` | `WorkspaceRenderer.tsx:159-182` |
| `access` | system | `AccessCenter` | `WorkspaceRenderer.tsx:183-185` |
| `research` | system | `ResearchDataWorkspace` | `WorkspaceRenderer.tsx:187-189` |
| `agents` | system | `AgentsWorkspace` | `WorkspaceRenderer.tsx:191-193` |
| `runtime` | system | `RuntimeWorkspace` | `WorkspaceRenderer.tsx:195-209` |
| `settings` | system | `SettingsCenter` | `WorkspaceRenderer.tsx:210-229` |
| `manual` | system | `ManualWorkspace` | `WorkspaceRenderer.tsx:230-236` |

Notes:

- `network` is the only page id intercepted by the shell; the other 15 go through
  `WorkspaceRenderer` (`clients/web/src/app/shell/AppShell.tsx:166-226`).
- The shell also sets a body-level class `workspace-${navigation.activeWorkspace}`
  (`AppShell.tsx:97`).
- `WorkspaceRenderer` imports `ContractWorkbench`, `MarketPositioningWorkspace`,
  `ReviewWorkspace` and `ScenarioWorkspace`
  (`clients/web/src/app/workspaces/WorkspaceRenderer.tsx:8, 11, 15, 18`) but never renders them
  (they are rendered by their parent workspaces). Observation: dead imports; no behaviour impact.
- **Risk - `orders` page id vs. Exposure task (observed mismatch, not a proven defect; no runtime
  change made):** the technical page id `orders` is labelled "Market Positioning"
  (`clients/web/src/i18n/en.json:11`), and `MarketPositioningWorkspace` renders that same label as
  its eyebrow (`clients/web/src/components/MarketPositioningWorkspace.tsx:43`). The portfolio task
  resolver, however, reads **only** `?task=` and defaults to `overview`
  (`clients/web/src/app/model/commercialWorkflowModel.ts:14-17`, called from
  `clients/web/src/components/PortfolioWorkspace.tsx:150-165`). Consequences at HEAD `dd1abe1`:
  - `?workspace=orders` renders the Portfolio shell with the **Overview** task, i.e. the label and
    the mounted surface disagree;
  - `?workspace=orders&task=exposure` renders Market Positioning - the same content as
    `?workspace=contracts&task=exposure`, because the task, not the page id, selects it;
  - no in-app navigation produces `?workspace=orders`: the portfolio task tabs call
    `navigation.openWorkspace("contracts", next)` (`PortfolioWorkspace.tsx:160-163`), and the only
    other `orders` consumers are the i18n label, the manual guide
    (`clients/web/src/components/ManualWorkspace.tsx:20`) and test fixtures
    (`tests/contract/test_workspace_navigation_contract.py:32, 45`;
    `clients/web/tests/productNavigation.test.ts:47, 74, 88`).
  Compare `decisionTaskFromLocation` (`commercialWorkflowModel.ts:19-28`), which does carry an
  explicit legacy `?workspace=review` branch (`clients/web/tests/commercialWorkflow.test.ts:37-38`);
  the portfolio resolver has no equivalent branch, so a bookmarked `?workspace=orders` entry lands
  on Overview instead of Market Positioning.
- Task-tab switching always rewrites the page id to `contracts`
  (`clients/web/src/app/model/commercialWorkflowModel.ts:30-35`), so the `orders` page id is
  reachable only by deep link/history entry, never by clicking a task tab.

### 2.5 Task tabs inside primaries (a second, local navigation layer)

| Shell | Tasks | Task resolution | Reference |
|---|---|---|---|
| Market | `overview`, `curves`, `network`, `capacity` | live resolver `resolveMarketViewTask`: URL `?task=` > `?workspace=network`/`capacity` (unreachable here - shell intercepts `network`; §2.3) > persisted per-principal view (`curves`/`network`) > `curves` default | `clients/web/src/components/MarketCockpit.tsx:261-272`; `clients/web/src/app/context/useMarketViewPreference.ts:50`; `clients/web/src/app/context/viewPreference.ts:202-215` |
| Portfolio | `overview`, `resources`, `routes`, `exposure` | `?task=exposure|routes|resources`, else `overview`; no `?workspace=` legacy branch, so `?workspace=orders` alone shows `overview` (§2.4) | `clients/web/src/app/model/commercialWorkflowModel.ts:11-17`; `clients/web/src/components/PortfolioWorkspace.tsx:150-165` |
| Decision | `scenario`, `optimize`, `review` | `decisionTaskFromLocation`: legacy `?workspace=review` **wins over** `?task=` (`?workspace=review&task=optimize` → `review`), then `?task=optimize|review`, then `?workspace=optimize`, else `scenario` | `clients/web/src/app/model/commercialWorkflowModel.ts:19-28`; `clients/web/tests/commercialWorkflow.test.ts:35-39`; `clients/web/src/components/DecisionWorkspace.tsx:127-156` |
| Strategy | `design`, `backtest`, `compare`, `shadow` | `strategyTaskFromLocation`: `?task=` (unknown → `design`); task switches are written with `history.pushState` | `clients/web/src/app/model/strategyLabModel.ts:14-29`; `clients/web/src/app/model/useStrategyLab.ts:42-58, 97-100` |
| System pages | `SourceCenter` (`attention/catalog/access/infrastructure`), `RuntimeWorkspace` (`readiness/delivery/governance`), `AccessCenter` (`users/api_keys/audit/sso`), `ResearchDataWorkspace` (`datasets/features/targets`), `AgentsWorkspace` (`capabilities/research/runs`) | component-local `useState`, not URL-addressable | `SourceCenter.tsx:27-29, 117`; `RuntimeWorkspace.tsx:21-24, 98`; `AccessCenter.tsx:11-12, 26`; `ResearchDataWorkspace.tsx:53-56, 542`; `AgentsWorkspace.tsx:20-22, 31` |

The unmounted `StrategyShadowRunTerminal` keeps its own four local views
(`clients/web/src/components/StrategyShadowRunTerminal.tsx:63, 253-265, 605-621`); because that
module is not mounted (§2.8) those tabs are not a current user-facing navigation layer and are
listed as re-activation detail only.

Observation (risk, not proven defect): system-area tabs and rails are not addressable by URL,
so their state is lost on deep-link/reload while market/portfolio/decision/strategy tabs are
URL-addressable. This is inconsistent interaction grammar relative to
`docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md:110-144`.

### 2.6 Selection mechanisms in use

| Mechanism | State | Persistence | Reference |
|---|---|---|---|
| Cross-workspace selection (`routeId`, `resourceId`, `strategyId`, `strategyVersionId`, `strategyRunId`) | `useSelectionContext` | URL query + history state, gated by identity | `clients/web/src/app/context/useSelectionContext.ts:22-96`; `selectionContext.ts:1-31` |
| Trader context (`gasDay`, `deliveryProduct`, `hubId`) | `useTraderContext` | URL query + `localStorage` + history state, gated by identity | `clients/web/src/app/context/useTraderContext.ts:27-97`; `traderContext.ts:1-67`; `contextPersistence.ts:1-60` |
| Market landing view | `useMarketViewPreference` | `localStorage` key `eurogas.marketView.v1`, scoped by principal | `clients/web/src/app/context/viewPreference.ts:20-115, 137-193`; `useMarketViewPreference.ts:1-52` |
| Cockpit controls (map layers, map search term) | `useCockpitControls` | in-memory only | `clients/web/src/app/hooks/useCockpitControls.ts:1-16` |
| Contract draft (`ContractDraft`) | `useContractEditor` | in-memory (+ file import) | `clients/web/src/app/hooks/useContractEditor.ts:1-71` |
| Source center, glossary, access, runtime, research, agents local state | component/hook `useState` | in-memory (reset with the identity-scoped resets) | see §2.5 rows; `clients/web/src/app/hooks/useSourceCenterController.ts:42-165`; `clients/web/src/app/hooks/useGlossaryExplorer.ts:19-95` |
| Language, theme | i18n + zustand store | `localStorage` (`eurogas.language.v1`, `theme`) | `clients/web/src/i18n/language.ts:13-65`; `clients/web/src/stores/theme.ts:1-25` |

There is **no** canonical Active Context object, no shared inspector selection model and no
work-mode state; each surface composes its own view of `api` state (§6).

### 2.7 Visible access gates (UI level)

| Gate | Where | Condition | Reference |
|---|---|---|---|
| Identity | whole shell | `authState === "authenticated"` | `AppShell.tsx:60-82`; `clients/web/src/stores/workspaceLoading.ts:17-40` |
| Release compatibility | whole shell | not a blocking compatibility state | `AppShell.tsx:31-58`; `clients/web/src/app/releaseCompatibility.ts:1-170` |
| Platform admin (Access Center) | `access` page + top-bar button | `currentUser.permissions.includes("identity.manage")` | `clients/web/src/components/AccessCenter.tsx:33-81`; `WorkspaceTopBar.tsx:207-217` |
| Optimizer run gate | Network / Scenario / Decision optimize | `runtimeDbReady && hasPortfolioResources && saleOptions.length > 0 && no blockers` | `clients/web/src/app/model/usePortfolioDecisionModel.ts:196-220, 320-323` |
| Route compare gate | Scenario | `hasPortfolioResources && saleOptions.length > 0` | `DecisionWorkspace.tsx:165` |
| Dev credential login | sign-in screen | backend advertises `dev_login` in `GET /api/auth/status`; no client env switch can enable it | `clients/web/src/stores/authGate.ts:53-59`; `SignInScreen.tsx:36-44` |

Explicitly recorded: the inventory found **no** page-level permission gate other than the Access
Center check. Two statements must be kept apart:

- What was inspected: UI gates only, over `clients/web/src` at `dd1abe1` (the check is a static
  search for permission conditions in components plus the Access Center gate above). It is an
  observation about the client, not an audit of backend authorization.
- What the architecture requires: backend enforcement is authoritative and UI visibility is not a
  security boundary (`docs/engineering/Architecture-V2/02_ARCHITECTURE_CONSTITUTION.md:31-40`,
  rules 16-23). This repair did not verify backend enforcement per route; §4.1/§4.7 only confirm
  that the client calls paths present on the pinned `/api` surface
  (`tests/contract/test_api_surface_stability.py:15-179`), which is a path-presence check, not an
  authorization or payload check.

### 2.8 Strategy shadow surface: mounted shell vs. transitive reference vs. unmounted terminal

Static references and user reachability are different claims; this section keeps them apart
(reference search over `clients/web/src`, 2026-09-14, HEAD `dd1abe1`):

- **Mounted user path (reachable today):** the `strategy` page mounts `StrategyLabWorkspace`,
  which renders `StrategyShadowShell` for task `shadow`
  (`clients/web/src/components/strategy/StrategyLabWorkspace.tsx:8, 94-100`).
  `StrategyShadowShell.tsx` is self-contained: it reads shadow monitors/alerts/status/evaluations/
  drift through the shared client (§4.5) and uses its own local `useState` selection
  (`clients/web/src/components/strategy/StrategyShadowShell.tsx:43-59, 65-99`).
- **Transitively referenced, not mounted:** `clients/web/src/components/StrategyShadowRunTerminal.tsx`
  imports `StrategyShadowRunSections` - five value imports plus five type imports
  (`clients/web/src/components/StrategyShadowRunTerminal.tsx:11-17, 18-24`) - so
  `clients/web/src/components/strategy/StrategyShadowRunSections.tsx` is referenced by exactly one
  module. That module is itself unmounted, so the reference chain does not make either component
  reachable in the running client.
  The first revision of this file incorrectly described both files as unreferenced; the reference
  was missed because the import is a multi-line named-import block ending in the module specifier.
- **Unmounted terminal:** `StrategyShadowRunTerminal` is referenced only inside its own file -
  its props interface (`:34`), declaration (`:220-235`) and no import site anywhere under
  `clients/web/src` (scripted search, see §8.2 item 4). It is the 845-line legacy evaluation
  terminal; if it is ever re-mounted it also uses a bespoke tab keyboard handler rather than the
  shared `WorkspaceTabs` primitive (`:63, 253-265, 605-621`).
  Whether to re-mount or retire it is an owner/Astra question (§9 item 5), not decided here.

## 3. Panel / detail / Inspector patterns (current)

### 3.1 Shared primitives that exist

`clients/web/src/components/ui/index.ts:1-10` exports `MetricStrip`, `PanelHeader`,
`StatusBadge`, `WorkspaceHeader`, `WorkspaceTabs`; `tabKeyboard.ts` holds the tab keyboard model
(`clients/web/src/components/ui/tabKeyboard.ts:1-15`).

| Primitive | Consumers (measured by import) |
|---|---|
| `WorkspaceTabs` | `WorkspaceTopBar`, `WorkspaceRenderer`, `SourceCenter`, `RuntimeWorkspace`, `AccessCenter`, `ResearchDataWorkspace`, `AgentsWorkspace`, `StrategyLabWorkspace` |
| `WorkspaceHeader` | `MarketCockpit`, `PortfolioWorkspace`, `DecisionWorkspace` |
| `PanelHeader` | `SourceCenter`, `RuntimeWorkspace`, `AccessCenter`, `ResearchDataWorkspace`, `AgentsWorkspace`, `AgentReviewGate`, `AgentArtifactChain` |
| `MetricStrip` | `SourceCenter`, `RuntimeWorkspace`, `ResearchDataWorkspace`, `AgentsWorkspace`, `AgentArtifactChain` |
| `StatusBadge` | `WorkspaceTopBar`, `SourceCenter`, `RuntimeWorkspace`, `AccessCenter`, `ResearchDataWorkspace`, `SettingsCenter`, `AgentArtifactChain`, `AgentReviewGate` |

`tests/contract/test_ui_primitives.py` enforces one home for these primitives and forbids new UI
frameworks.

### 3.2 Local patterns that do not use the shared primitives

- Network decision rail: four local tab buttons (`decision|pnl|warnings|evidence`) rendered with
  bespoke markup instead of `WorkspaceTabs` (`clients/web/src/components/NetworkWorkspace.tsx:39, 182, 361-375`).
- Market spread strip, hub board and context rail are bespoke `data-table`/`panel` markup
  (`MarketCockpit.tsx:134-246`).
- Strategy identity header / navigator are bespoke (`clients/web/src/components/strategy/StrategyNavigator.tsx`,
  `StrategyIdentityHeader.tsx`).

### 3.3 Detail patterns in use

| Pattern | Example | Reference |
|---|---|---|
| Master–detail with right rail | Research datasets catalog + detail rail | `ResearchDataWorkspace.tsx:428-501, 819` |
| Drawer / popover | Monitoring alert drawer in the top bar | `clients/web/src/components/AlertCenter.tsx:48-70` |
| Right side rail with local tabs | Network decision rail | `NetworkWorkspace.tsx:361-529` |
| Collapsible `<details>` cards | Pool allocation cards, intraday opportunities | `NetworkWorkspace.tsx:392-423`; `IntradayDecisionFeed.tsx:66-107` |
| In-page form + result panels | Contract draft, scenario economics, strategy design | `PortfolioWorkspace.tsx:182-210`; `DecisionWorkspace.tsx:158-176`; `StrategyDesignWorkspace.tsx` |
| Table + inline action buttons | Access users/keys/audit | `AccessCenter.tsx:108-196` |
| Artifact chain timeline | Agent replay review pack | `clients/web/src/components/agents/AgentArtifactChain.tsx`; `AgentsWorkspace.tsx:279-345` |

### 3.4 Concepts explicitly absent or uncertain today

| Target concept (`04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`) | Status today |
|---|---|
| Canonical Inspector | Absent as a shared component; each workspace has its own detail surface (§3.3) |
| Panel taxonomy registry | Absent; panel types are CSS classes (`workspace-panel`, `metric-grid`, `data-table`) |
| Command palette / global shortcut model | Absent. Only tab-keyboard handling exists (`tabKeyboard.ts`; `WorkspaceTabs.tsx:37-45`). No global `keydown` listener was found in `clients/web/src` |
| Global Activity / Jobs / Timeline surface | Absent. Runtime health (`/runtime/pipeline-health`) is shown only inside the `runtime` page; strategy runs, research builds/exports and agent runs are local to their workspaces |
| Notification centre | Partly present: `AlertCenter` shows monitoring alerts only (`AlertCenter.tsx:31-46`); endpoint failures show in the shell banner; there is no unified notification model |
| Copilot / cross-workspace AI | Absent. AI actions exist per surface: alert analysis, review analysis/report, agent research (§4) |
| Work modes / ExperienceProfile | Absent. Navigation is a fixed five-primary model (`productNavigation.ts:18-53`) |
| HostCapabilities contract | Absent. Host differences are detected by inline `__TAURI_INTERNALS__`/protocol/hostname checks (`clients/web/src/api/client.ts:10-13`; `clients/web/src/stores/api.ts:1022-1026`) |
| Active Context / Analysis Snapshot / Decision Case objects | Absent. Closest current artefacts are the URL/query context, optimizer results and `review_decisions` rows |

## 4. Per-surface API dependency map (traced through hooks/services)

Transport is one shared client: `clients/web/src/api/client.ts` (method table `:1821-2158`;
`get/patch/put/post` helpers `:381-423`; `openEventStream` `:216-245`).
Every workspace reads a reactive slice of one zustand store `clients/web/src/stores/api.ts`
(`ApiState` at `:191-288`) unless noted otherwise.

### 4.1 Shell / global (always mounted while authenticated)

| Call | HTTP + endpoint | Call site |
|---|---|---|
| `api.me` (`GET /me`) + `api.authStatus` (`GET /auth/status`) in parallel on boot | `GET /me`, `GET /auth/status` | `stores/api.ts:502-550` |
| `api.runtimeRelease` (`GET /runtime/release`) — release gate before the batch | `GET /runtime/release` | `stores/api.ts:585-604` |
| `WORKSPACE_LOADERS` batch: referenceNodes, referenceEdges, sources, normalizedMarkets, marketSpreads, marketQuotes, intradayOpportunities, screenOrders, pnlSnapshots, portfolioSummary, fxRates, flows, capacity, storage, lng, tsoAccess, routes, routeCandidates, tsoTariffs, upstreamContracts, resourcePoolOptions, glossaryTerms, runtimeDb, runtimeDependencies, credentialProviders, monitoringAlerts, monitoringSummary, reviewDecisions, pipelineHealth (29 loaders) | `GET /reference-network/nodes`, `/reference-network/edges`, `/sources`, `/market/normalized`, `/market/spreads`, `/market/quotes`, `/market/opportunities`, `/portfolio/screen-orders`, `/portfolio/pnl-snapshots`, `/portfolio/live-summary`, `/market/fx`, `/physical/flows`, `/physical/capacity`, `/storage/observations`, `/lng/observations`, `/reference-network/tso-access`, `/contracts/routes`, `/route-cost/route-candidates`, `/route-cost/tso-tariffs`, `/route-cost/upstream-contracts`, `/route-cost/resource-pool/options`, `/glossary`, `/runtime/db`, `/runtime/dependencies`, `/credentials/providers`, `/monitoring/alerts`, `/monitoring/summary`, `/review/decisions`, `/runtime/pipeline-health` | Loader table `stores/api.ts:346-376`; commit `:619-694`; client methods `client.ts:1825-1945, 2119-2120, 1918-1921, 2073-2075, 2076-2096` |
| Follow-up reads after the batch | `GET /strategy-lab/summary`, `GET /strategy-lab/runs`, `GET /me` | `stores/api.ts:690-692` (then `fetchStrategySummary` `:1336-1348`, `fetchStrategyRuns` `:1350-1362`, `fetchMe` `:967-1005`) |
| SSE streams | `GET /stream/quotes`, `GET /stream/opportunities`, `GET /stream/alerts` | `stores/api.ts:896-965`; `client.ts:220-245` |
| Market refresh lane (10 s interval on `network`/`market`/`strategy` pages) | `GET /sources`, `/market/normalized`, `/market/spreads`, `/market/quotes`, `/market/opportunities`, `/market/fx` | `clients/web/src/app/hooks/useWorkspaceRuntime.ts:6-21, 50-58`; `stores/api.ts:767-894` |
| Monitoring refresh lane (10 s when SSE is not live) | `GET /monitoring/alerts`, `/monitoring/summary`, `/runtime/pipeline-health` | `useWorkspaceRuntime.ts:60-67`; `stores/api.ts:1098-1167` |
| Endpoint retry | re-issues only the failed loaders | `stores/api.ts:697-765`; button `AppShell.tsx:150-160` |
| Alert drawer actions | `POST /monitoring/alerts/{id}/acknowledge`, `POST /monitoring/alerts/{id}/analysis` | `stores/api.ts:1210-1250`; `client.ts:1923-1932`; mount `WorkspaceTopBar.tsx:173-181` |
| Desktop SSO | `POST /auth/oidc/desktop/login`, `POST /auth/oidc/desktop/token`, `POST /auth/logout`, browser redirect to `/auth/oidc/login` | `stores/api.ts:1007-1096`; `client.ts:2140-2144` |
| Dev credential sign-in (only if backend advertises it) | `POST /dev/auth/login` | `stores/api.ts:552-578`; `client.ts:2138-2139` |

### 4.2 Market primary (`network`, `market`, `capacity`)

| Surface | Data dependencies | Reference |
|---|---|---|
| `NetworkWorkspace` (standalone page and market task) | Consumes slices only; the only server action is the optimizer `POST /route-cost/resource-pool/optimize` via `onOptimizePool` | `clients/web/src/app/shell/AppShell.tsx:168-224`; `MarketCockpit.tsx:304-353`; `usePortfolioDecisionModel.ts:320-323` |
| `MarketOverview` task | reads `normalizedMarkets`, `marketQuotes`, `intradayOpportunities`, `nodes`, `edges`, `routes`, `flows`, `capacity`, `storage`, `lng`, `routeCandidates`, `tsoAccess`; refresh button calls `refreshMarketData()` | `MarketCockpit.tsx:88-249` |
| `MarketTerminal` (curves) | `normalizedMarkets`, `marketSpreads`, `marketQuotes`, `intradayOpportunities`, `fxRates`, `sources` | `MarketCockpit.tsx:289-303`; `clients/web/src/components/MarketTerminal.tsx:14-26` |
| `CapacityWorkspace` | `flows`, `capacity`, `tsoAccess`, `tsoTariffs`, `storage`, `lng` | `MarketCockpit.tsx:355-365`; `clients/web/src/components/CapacityWorkspace.tsx:16-24` |

No market surface issues direct `fetch`/vendor calls; map tiles are the only third-party request
(§6.5).

### 4.3 Portfolio primary (`contracts`, `orders`)

| Surface | Call | Endpoint | Reference |
|---|---|---|---|
| Portfolio overview | reads `resourcePoolOptions`, `resourcePoolResult`, `routeRecommendation` | — | `PortfolioWorkspace.tsx:21-96` |
| Resource terms (task `resources`) | `api.saveDraftContract` → follow-up reads `upstreamContracts` + `resourcePoolOptions` | `POST /route-cost/upstream-contracts`, then `GET /route-cost/upstream-contracts`, `GET /route-cost/resource-pool/options` | `PortfolioWorkspace.tsx:183-209`; `stores/api.ts:1252-1275`; `client.ts:1940-1945` |
| Contract import | File-read + JSON/text parse only; no network | `clients/web/src/app/hooks/useContractEditor.ts:47-66`; `clients/web/src/app/contractImport.ts` |
| Route comparison (task `routes`) | reads `routeCandidates`, `resourcePoolResult`, `routeRecommendation`, `resourcePoolOptions`; row click sets route selection and opens Scenario | — | `PortfolioWorkspace.tsx:98-148` |
| Market positioning (`MarketPositioningWorkspace`) | reads `portfolioSummary`, `screenOrders`, `pnlSnapshots`; no call of its own | — | mounted at `clients/web/src/components/PortfolioWorkspace.tsx:212-220` **only** for task `exposure`, i.e. `?workspace=orders&task=exposure` or `?workspace=contracts&task=exposure`; `?workspace=orders` alone renders the overview task (§2.4); component at `clients/web/src/components/MarketPositioningWorkspace.tsx:32-88` |

### 4.4 Decision primary (`scenario`, `review`, `optimize`)

| Surface | Call | Endpoint | Reference |
|---|---|---|---|
| Scenario compare/optimize buttons | `portfolio.optimizeResourcePoolForCurrentContext()` / `recommendRouteAllocationForCurrentContext()` | `POST /route-cost/resource-pool/optimize`, `POST /route-cost/recommend` | `DecisionWorkspace.tsx:173-174`; `usePortfolioDecisionModel.ts:320-328`; `stores/api.ts:1296-1322` |
| Optimize task | same optimizer mutation | as above | `DecisionWorkspace.tsx:19-125, 177` |
| Review analysis | `askAnalysis` | `POST /analysis/query` | `DecisionWorkspace.tsx:195`; `stores/api.ts:1379-1392`; `client.ts:2128` |
| Review report | `generatePortfolioReport` | `POST /reports/portfolio` | `DecisionWorkspace.tsx:196`; `stores/api.ts:1394-1407`; `client.ts:2130` |
| Review decision recording | `recordReviewDecision` (store action passed down as a prop) | `POST /review/decisions`, then `GET /review/decisions` | `DecisionWorkspace.tsx:197`; `stores/api.ts:1277-1294`; `client.ts:1863-1867` |

### 4.5 Strategy primary (`strategy`)

`useStrategyLab` owns its own state and calls the shared client directly
(`clients/web/src/app/model/useStrategyLab.ts:10, 102-236`):

| Action | Endpoint | Reference |
|---|---|---|
| Load strategy list | `GET /strategies` | `useStrategyLab.ts:102-109`; `client.ts:1972` |
| Load versions of a strategy | `GET /strategies/{id}/versions` | `useStrategyLab.ts:111-124`; `client.ts:1982-1983` |
| Load registered runs | `GET /strategy-runs?strategy_id=&limit=50` | `useStrategyLab.ts:126-139`; `client.ts:2003-2011` |
| Load run detail | `GET /strategy-runs/{id}/events`, `/series`, `/attribution` | `useStrategyLab.ts:178-195`; `client.ts:2016-2023` |
| Run a backtest | `POST /strategy-runs` then refresh + detail load | `useStrategyLab.ts:197-236`; `client.ts:2000-2001` |
| Design: create/version/freeze/fork | `POST /strategies`, `POST /strategies/{id}/versions`, `PUT /strategy-versions/{id}/draft`, `POST /strategy-versions/{id}/fork`, `POST /strategy-versions/{id}/freeze` | `clients/web/src/components/strategy/StrategyDesignWorkspace.tsx:236-283` |
| Shadow shell | `GET /shadow-monitors`, `GET /shadow-alerts`, `GET /shadow-runtime/status`, `GET /shadow-monitors/{id}/evaluations`, `GET /shadow-monitors/{id}/drift`, `POST /shadow-monitors`, `POST /shadow-monitors/{id}/pause|resume|retire`, `POST /shadow-alerts/{id}/acknowledge` | `clients/web/src/components/strategy/StrategyShadowShell.tsx:65-133, 303`; `client.ts:2033-2069` |
| Lab evaluation (legacy path still reachable through the portfolio model) | `POST /strategy-lab/evaluate` | `usePortfolioDecisionModel.ts:330-349`; `stores/api.ts:1324-1334`; `client.ts:1953-1954` |

### 4.6 System primary

| Page | Call / dependency | Endpoint(s) | Reference |
|---|---|---|---|
| `sources` | reads `sources`, `credentialProviders`, `flows`, `capacity`, `storage`, `lng`, `tsoAccess`, `tsoTariffs`, `latestCapacityRows`; credential actions `saveProviderCredential` / `testProviderConnection` | `PUT /credentials/{provider_id}`, `POST /credentials/{provider_id}/connection-test`, then `GET /credentials/providers` | `WorkspaceRenderer.tsx:121-158`; `useSourceCenterController.ts:88-97, 157-159`; `stores/api.ts:1169-1208`; `client.ts:1903-1916` |
| `glossary` | reads `glossaryTerms`; context fetch `fetchGlossaryContext(term, {lang, duration_start_utc, duration_end_utc})` | `GET /glossary/{term}/context` (dynamic term) | `WorkspaceRenderer.tsx:159-182`; `useGlossaryExplorer.ts:60-75`; `stores/api.ts:1364-1377`; `client.ts:2122-2126` |
| `runtime` | reads `meta`, `runtimeDb`, `pipelineHealth`, `runtimeDependencies`, `sources`, `streamingActive`, `endpointErrors`; refresh button calls `refreshMonitoring` | `GET /monitoring/*`, `GET /runtime/pipeline-health` | `WorkspaceRenderer.tsx:195-209`; `RuntimeWorkspace.tsx:86-120` |
| `settings` | `testApiBaseUrl` against a candidate base then `onBackendBaseChanged` → `fetchWorkspace`; stores API base, API token, operator principal, map tile provider/token, language, theme, market view | `GET /health`; then the full workspace batch | `SettingsCenter.tsx:187-207, 277-283, 319-340, 355-370`; `WorkspaceRenderer.tsx:210-229` |
| `manual` | No API call of its own; reads `runtimeDb`, active source count, tariff count, open-order count | — | `WorkspaceRenderer.tsx:230-236`; `clients/web/src/components/ManualWorkspace.tsx:14-64` |
| `access` | `GET /access/users`, `GET /access/api-keys`, `GET /audit?limit=100`, `GET /access/sso`; mutations `PATCH /access/users/{principal_id}`, `POST /access/api-keys/{key_id}/revoke` | as listed | `AccessCenter.tsx:35-70`; `client.ts:2145-2157` |
| `research` | catalog `GET /research/features`, `/research/targets`, `/research/datasets`; detail `GET /research/datasets/{id}` + `/quality`; validate `POST /research/datasets/validate`; build `POST /research/datasets`; export `POST /research/datasets/{id}/export` | as listed | `ResearchDataWorkspace.tsx:611-648, 657-678, 705-800`; `client.ts:2076-2093, 2110-2117` |
| `agents` | `GET /capabilities` + `GET /agent/runs` on mount; `POST /agent/research`; `GET /agent/runs/{id}/replay`; review confirmation `POST /review/decisions` (non-throwing outcome variant) | as listed | `AgentsWorkspace.tsx:42-54, 67-140`; `client.ts:2101-2111, 1877-1878` |

### 4.7 Shared-client methods with no call-site reference (26 of 117)

Rule used (scripted, 2026-09-14): for each method declared in the `api` object
(`clients/web/src/api/client.ts:1821-2158`), search `clients/web/src` excluding the client
definition itself for a reference of the form `api.<name>`, `apiClient.<name>` or
`client.api.<name>`. 91 of 117 have such a reference; the 26 names below have none. A looser
bare-identifier search returns 21 instead, because `health`, `strategy`, `netback`, `capability`
and `marketObservations` also occur as unrelated property/label names; that looser rule is not used
here. No call-site reference means below only that:
`health`, `facilities`, `marketHubs`, `marketObservations`, `strategyRun`, `strategy`,
`updateStrategyMetadata`, `strategyVersion`, `strategyRegistryRun`, `createBacktestExperiment`,
`backtestExperiments`, `backtestExperiment`, `shadowMonitor`, `shadowEvaluation`,
`capacityContracts`, `researchCapabilities`, `searchCapabilities`, `capability`,
`invokeCapability`, `agentProfiles`, `agentRun`, `routeCost`, `netback`, `accessRoles`,
`accessDataScopes`, `createAccessApiKey`.
Scope of this list (kept explicit because it is easy to over-read):

- It is the result of a **static reference search** over `clients/web/src` excluding the client
  definition itself: none of these 26 method names appears as `api.<name>`, `apiClient.<name>` or
  `client.api.<name>` anywhere else in that tree. (Some of the names do occur as unrelated
  identifiers - see the looser-rule note above.)
- It is **not** a runtime reachability proof. A statically referenced method can still be
  unreachable, and the converse also holds: §2.8 shows a component that *is* statically referenced
  (transitively) while remaining unmounted. No runtime trace, build or coverage run was performed.
- "Present on the pinned `/api` surface" is likewise a path-presence statement only:
  `tests/contract/test_api_surface_stability.py:15-179` pins the OpenAPI path set
  (`:188-199`), so a listed path proves the route exists on the surface - not that a client can
  call it, nor what authorisation or payload it requires.

Kept because it is relevant to the V2 "missing UI is not waived" rule
(`docs/engineering/RFC-0001-UI-CONVERGENCE.md:46-48`). Listed as observation, not as a defect.

## 5. Shared client services, loading, streaming and retry (current)

### 5.1 Transport (`clients/web/src/api/client.ts`)

- URL building: `apiUrl`/`apiUrlForBase` (`:208-214`), base normalisation (`:104-125`).
- Parse/error: `parseResponse` maps non-2xx to `API <status>: <detail>` messages (`:342-372`);
  `ApiOutcome` variant returns failures instead of throwing (`:326-340`).
- Limits baked into the client: reference-network reads `limit=2000` (`:5`), normalized market
  `limit=500` (`:1859`), quotes `limit=500` (`:1882`), opportunities `limit=100` (`:1885`),
  monitoring alerts `limit=100` (`:1919`).
- Only two endpoint templates interpolate a path segment **without** `encodeURIComponent`:
  `/credentials/${providerId}` and `/credentials/${providerId}/connection-test`
  (`client.ts:1906, 1914`). Every other dynamic segment uses `encodeURIComponent`.
  Recorded as a consistency observation; `providerId` originates from the server-provided
  provider list.

### 5.2 Store orchestration (`clients/web/src/stores/api.ts`)

- Independent endpoint deadlines and retry: `loadEndpointWithRetry` (`:325-337`),
  `loadWorkspaceEndpoints`/`loadWorkspaceEndpoint` from `workspaceLoading.ts:141-268`,
  10 s default read timeout and 5 s logout timeout (`workspaceLoading.ts:1-2`).
- Identity guard: every loader procedure returns early unless `isIdentityGateOpen` (`:582, 699, 769, 899, 1100`).
- Generation guards: `WorkspaceLoadCoordinator`, `ReadRefreshCoordinator`,
  `IdentityReadCoordinator` (`:93-97`) protect late responses from previous identities.
- Failure taxonomy surfaced to the UI: `timeout | aborted | request`
  (`workspaceLoading.ts:42-47`) with per-endpoint keys and codes (`:240-248`).
- Data-status derivation from source references and runtime DB state
  (`:629-641`), rendered as Ready/Partial/Unavailable (`WorkspaceTopBar.tsx:190-205`).

### 5.3 Polling / streaming summary

| Mechanism | Interval / trigger | Scope |
|---|---|---|
| SSE `stream/quotes`, `stream/opportunities`, `stream/alerts` | on workspace load; closed on identity change or sign-out | quotes/opportunities/alerts slices (`stores/api.ts:896-965`) |
| Market refresh | every 10 s while the active page is `network`, `market` or `strategy` | market slice + sources (`useWorkspaceRuntime.ts:6-21, 50-58`) |
| Monitoring refresh | every 10 s when SSE is not live | alerts, summary, pipeline health (`useWorkspaceRuntime.ts:60-67`) |
| UI timers | one `setTimeout` for market-overview expiry re-render | `MarketCockpit.tsx:92-102` |

No other polling interval exists in `clients/web/src` (verified by searching `setInterval`).

## 6. Observed composition/waterfalls, joins and derived values

### 6.1 Boot/first-paint waterfall

1. `hydrateApiBaseUrlFromDesktopDeployment()` → `bootstrapIdentity()`
   (`useWorkspaceRuntime.ts:34-42`).
2. `bootstrapIdentity` → parallel `GET /me` + `GET /auth/status`; identity denial clears all
   identity-scoped slices and shows the sign-in screen (`stores/api.ts:502-550`).
3. On authentication → `fetchWorkspace()`: release read first, then the 29-endpoint batch, then
   commit, then 3 follow-up reads (`strategy summary`, `strategy runs`, `me`), then streams
   (`stores/api.ts:580-694`).
4. Streams and the 10 s market lane start afterwards (`useWorkspaceRuntime.ts:50-67`).

First paint therefore waits for identity, and the terminal renders partially-loaded workspaces
with a per-endpoint banner rather than blocking.

### 6.2 Client-side reconstruction (waterfall) examples

| Composite value | Inputs joined in the client | Reference |
|---|---|---|
| Portfolio resources / sale options / total volume | `resourcePoolOptions` | `usePortfolioDecisionModel.ts:66-85` |
| Optimizer request | `contract` draft + resources + sale options + `upstreamContracts` | `usePortfolioDecisionModel.ts:94-102`; `clients/web/src/app/resourcePoolRequest.ts` |
| Route recommendation request | resources + sale options + total volume + contracts | `usePortfolioDecisionModel.ts:103-111` |
| Decision PnL (3-step fallback) | `resourcePoolResult.total_net_pnl_gbp_per_day` → `routeRecommendation.allocations[0]` (netback × volume) → `portfolioSummary.total_indicative_pnl_gbp` | `usePortfolioDecisionModel.ts:130-137` |
| Purchase/sale/route price for the PnL rail | first pool allocation, first resource, first sale option, route recommendation allocation | `usePortfolioDecisionModel.ts:138-145` |
| Scenario route economics | `routeRecommendation` + `resourcePoolResult` + `saleOptionById` + selected resource | `usePortfolioDecisionModel.ts:146-163`; `clients/web/src/app/model/scenarioRouteEconomics.ts:44-96` |
| Evidence stack (max 6 items) | warnings + blockers + missing inputs + assumptions + `source_refs` from results, `meta` and every endpoint meta | `usePortfolioDecisionModel.ts:284-314` |
| Network geometry state | runtime DB ready + nodes + edges | `usePortfolioDecisionModel.ts:315-318`; `clients/web/src/app/workspaceDerivedData.ts` |
| Capacity "latest rows" | flows + capacity + tso access + tariffs + storage + lng | `usePortfolioDecisionModel.ts:169-179`; `workspaceDerivedData.ts` |
| Route feasibility classification | route candidates + recommendation + optimizer result + pool options (blockers authoritative) | `clients/web/src/app/model/commercialWorkflowModel.ts:63-122` |
| Strategy scenario payload | contract draft + a client-side placeholder live mark (`venue: "ICE OCM"`, hub/product fixed, prices `null`) + context-filtered market observations + resources | `usePortfolioDecisionModel.ts:55-64, 112-121`; `clients/web/src/app/strategyScenario.ts:88-190` |

Risks (evidence-backed, not proven defects):

- R1 **Automatic optimizer mutation on data change**: when the pool signature changes and the
  gate is open, the client automatically POSTs `/route-cost/resource-pool/optimize` without an
  explicit operator action (`usePortfolioDecisionModel.ts:221-253`). This is a mutation triggered
  by a render effect; the V2 target moves business state to server projections
  (`docs/engineering/Architecture-V2/02_ARCHITECTURE_CONSTITUTION.md:52-58`, rules 31-35).
- R2 **Fallback-chain values**: `decisionPnl` mixes three different result layers and can print a
  value derived from `portfolioSummary` when no decision result exists
  (`usePortfolioDecisionModel.ts:130-137`). Each layer is individually labelled elsewhere, but the
  UI rail does not distinguish which layer produced the number.
- R3 **Placeholder live mark**: the strategy scenario payload carries a client-constructed
  "operator-draft-live-mark" with null prices (`usePortfolioDecisionModel.ts:55-64`), while the
  server price observations are joined separately (`strategyScenario.ts:88-190`). If a component
  ever renders the mark itself, it would show a placeholder; today it is only an input field.
- R4 **First-row picks**: several headline numbers are `allocations[0]` / `resources[0]`
  (`usePortfolioDecisionModel.ts:123-129, 164`), so displayed "current" values depend on server
  ordering rather than on an explicit selection.
- R5 **Client-side capacity/geometry derivation**: `workspaceDerivedData.ts` and
  `scenarioRouteEconomics.ts` compute display values (headroom, posture, indicative geometries)
  from multiple endpoints; V2 forbids critical commercial state reconstruction on the client
  (`docs/engineering/Architecture-V2/02_ARCHITECTURE_CONSTITUTION.md:57-58`, rules 34-35).
- R6 **Heuristic joins**: hub matching uses upper-cased substring matching
  (`MarketCockpit.tsx:114-119`), and the runtime workspace keeps a hard-coded licensed-vendor list
  (`RuntimeWorkspace.tsx:60-68`). Both are display heuristics; they are marked here so V2 does not
  inherit them silently.

### 6.3 Context joins (gas day / product / hub)

- Context filtering helper `marketMatchesTradingContext` is applied when joining market
  observations (`usePortfolioDecisionModel.ts:86-93`), and result-vs-context mismatch flags are
  computed for optimizer, route and strategy results
  (`clients/web/src/app/model/usePortfolioDecisionModel.ts:204-214`) and returned to the controller
  (`:365-367`). Appearance of the `context.result_mismatch` banner, verified against the mounted
  path rather than against the flag names:
  - `optimizerContextMismatch` is surfaced in Network
    (`clients/web/src/components/NetworkWorkspace.tsx:269-274`) and in Scenario
    (`clients/web/src/components/ScenarioWorkspace.tsx:71-80`, fed by
    `clients/web/src/components/DecisionWorkspace.tsx:170`). These are mounted (Network by the
    shell for `?workspace=network` and by the market `network` task; Scenario by the Decision
    primary).
  - `routeContextMismatch` and `strategyContextMismatch` have **no consumer** in `clients/web/src`
    (scripted reference search, 2026-09-14): they are computed and returned but never rendered.
  - Strategy currently shows **no** mismatch banner. The only strategy-side banner is in the
    unmounted `StrategyShadowRunTerminal` (`clients/web/src/components/StrategyShadowRunTerminal.tsx:629-634`,
    §2.8); the mounted `StrategyShadowShell` does not render one
    (`clients/web/src/components/strategy/StrategyShadowShell.tsx` has no `context.result_mismatch`
    reference). The first revision of this file cited the unmounted terminal as current Strategy
    behaviour; that claim is withdrawn.
- Feature sets differ: the market primary's own tasks use `traderContext` for hub focus
  (`MarketCockpit.tsx:113, 145-152`); capacity, glossary, sources, runtime and access surfaces do
  not consume the trader context.

### 6.4 Timestamp joins

| Joined value | Rule | Reference |
|---|---|---|
| `marketLastUpdatedAtUtc` | max of normalized observations, quotes and FX timestamps | `stores/api.ts:178-189, 681-685, 852-856` |
| Merged quotes/opportunities | dedupe by id, keep newest `observed_at_utc`/`detected_at_utc`, cap 500/100 | `stores/api.ts:146-176` |
| SSE quote update | max of previous value and the incoming quote timestamp | `stores/api.ts:915-921` |
| Source/capacity display freshness | local `Intl` formatting of the newest row per group | `useSourceCenterController.ts:128-136`; `workspaceDerivedData.ts` |

Observation: there is **no** shared "as-of" / snapshot identity across these joins; a single screen
can mix values captured at different times (e.g. `marketLastUpdatedAtUtc` from one endpoint and
allocation values from another). V2's Analysis Snapshot invariant is the target answer to this;
that is target direction, not current behaviour.

### 6.5 Client-side third-party requests (recorded for the licensing/entitlement question)

The only non-backend network calls found in `clients/web/src` are raster map tiles:
`clients/web/src/app/mapTileProviders.ts:16-49, 116-200` builds OSM/CARTO/AMap/Tianditu tile URLs
and `clients/web/src/components/GasNetworkMap.tsx:119-121, 251-262` mounts the style. A Tianditu
token can come from `localStorage` (`eurogas.settings.map_tile_token`, `:94-114`) or
`VITE_EUROGAS_MAP_TILE_TOKEN`. This is basemap imagery, not market data; whether the current
packaging is compliant with provider terms is a licence/entitlement interpretation question and is
listed as unresolved rather than decided here. No client code calls a market-data vendor API or a
database directly.

## 7. Current-to-target map (concise) and existing fitness checks

Decision vocabulary: KEEP / EVOLVE / REFACTOR / DEFER (per `11_CURRENT_TO_TARGET_GAP_MATRIX.md`).

| Area inventoried | Current evidence | Decision | Target note |
|---|---|---|---|
| One React UI, one transport client | `App.tsx` + `api/client.ts` single client | KEEP | Preserve; add application projections behind the same boundary |
| Technical page-id / route identity (`workspacePageIds`, incl. legacy ids `network`, `orders`, `review`) | `clients/web/src/workspaceNavigation.ts:1-49`; `clients/web/src/app/navigation/productNavigation.ts:18-54` | KEEP (compatibility only) | These ids are a live deep-link contract: existing bookmarks and history entries must keep resolving. Contract tests pin that contract (§7 checks below) - pinned compatibility is not the same as an accepted target composition. |
| Five-primary navigation composition (primary tabs + child pages) | `productNavigation.ts:18-54`; `clients/web/src/components/WorkspaceTopBar.tsx:92-109` | **REFACTOR** (V2 target direction) | `11_CURRENT_TO_TARGET_GAP_MATRIX.md:26` marks "Navigation: functional workspace based" as REFACTOR ("Shell + patterns + work-mode composition"), and `:24` marks "Market/Portfolio/Strategy pages: feature-centric" as REFACTOR. Deciding composition is an architecture decision for Astra/Wave 1, not something the passing contract tests settle; no ADR acceptance is implied by this row. |
| URL/query navigation contract | `useWorkspaceNavigation.ts`, context hooks | KEEP/EVOLVE | Keep deep links; V2 adds Active Context on top |
| Two navigation levels (primary tabs + local tasks) | §2.5 | EVOLVE | Workspace-pattern registry + shell contract in Wave 1 |
| Local task tabs on system pages (not URL-addressable) | §2.5 | REFACTOR | Converge on one navigation model |
| Shared primitives (`WorkspaceTabs`/`PanelHeader`/`MetricStrip`/`StatusBadge`) | `components/ui` | KEEP | Wave 9 applies them to remaining local patterns |
| Detail surfaces (rails, drawers, master-detail) | §3.3 | REFACTOR | Canonical Inspector (`docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md:97-108`) |
| Command palette / keyboard model | Absent | DEFER | Wave 1 contract first |
| Global Activity/Jobs/Notifications | Absent (alerts + endpoint banner only) | DEFER | Wave 8 Unified Job |
| AI actions | Alert analysis, review analysis/report, agent research | EVOLVE | Canonical Ask/Explain/Compare/Challenge/Draft (Wave 7) |
| Client business-state reconstruction | §6.2 R1–R6 | REFACTOR | Wave 5 projections / Active Context |
| Timestamp/context joins | §6.3–6.4 | REFACTOR | Analysis Snapshot invariant |
| Client-held API token / operator principal in `localStorage` | `clients/web/src/api/client.ts:6-8, 15-26, 44-86` | DEFER (record only) | Any change is a security-scope decision outside this task |
| Map tile third-party requests | §6.5 | DEFER | Licence/entitlement interpretation question |
| Dead imports; unmounted terminal and its transitively referenced sections | §2.4 note, §2.8 | DEFER | Cleanup or re-mount only with owner confirmation; reachability, not static references, is the evidence |

Reading note for this table: KEEP means "preserve through the migration / keep the current contract
working", not "approved target design"; REFACTOR rows follow `11_CURRENT_TO_TARGET_GAP_MATRIX.md`,
which is target direction. The fitness checks below are compatibility gates over today's contracts -
they are evidence about the current implementation and they constrain any migration, but they do not
ratify the present navigation composition as the V2 target.

Existing fitness checks relevant to this inventory (present in the repository today):

| Check | What it protects |
|---|---|
| `tests/contract/test_workspace_navigation_contract.py:92-214` | Page-id registry completeness, primary/child mapping completeness + uniqueness (`:123-139`), defaults, hook helpers, top-bar tabs, i18n parity for nav labels |
| `clients/web/tests/productNavigation.test.ts` | Same mapping as executable TypeScript, incl. uniqueness and legacy ids |
| `clients/web/tests/marketViewSeparation.test.ts` | Market numeric vs map task separation and single map mount |
| `clients/web/tests/viewPreference.test.ts` | Market view precedence and persistence |
| `tests/contract/test_web_client_structure.py` | `App.tsx` stays a ≤20-line composition root; renderer owns page wiring |
| `tests/contract/test_ui_primitives.py` | Shared primitives have one home; no UI framework added |
| `tests/contract/test_trader_context_contract.py` | Trader context / selection separation and no duplicated gas day |
| `tests/contract/test_client_release_surface.py` | Web/desktop/Cargo/pyproject version alignment; desktop wraps `web/dist` |
| `tests/contract/test_api_surface_stability.py` | The `/api` surface that every client path must stay inside |
| `clients/web/tests/*.test.ts` (26 files) | Model-level checks incl. auth gate, mutation identity guards, endpoint failures, research data, strategy lab, agent replay |

## 8. Verification performed for this artifact

Two records are kept separate: what the original run reported (8.1) and what this repair re-checked
(8.2). The historical `git diff --check` result was **not** clean; it is preserved as reported rather
than rewritten.

### 8.1 Historical record - original W0-01 run at HEAD `d42e71b`

Source: the worker result artifact for that run
(`.automation/runtime/worker_runs/W0-01-20260914-224834.final.json`, read-only).

1. `git rev-parse HEAD` → `d42e71b330c4df97c97c2d61b52f9e18f4d4c39b` (matched the brief baseline).
2. Route coverage: all 16 `workspacePageIds` traced to a mount site; all 5 primaries' children
   cross-checked against `primaryWorkspaces` → 16/16 covered.
3. Endpoint mapping (scripted extraction of client path literals vs the pinned surface):
   110 of 111 matched after normalising `${encodeURIComponent(...)}`; the only non-match was the
   base constant `"/api"`.
4. Client method census: 117 declared, 91 referenced elsewhere in `clients/web/src`, 26 with no
   call-site reference.
5. Citation check (scripted): 76 distinct cited files, 202 line references, 0 missing and
   0 out-of-range.
6. `git diff --no-index --check -- /dev/null <new file>` → no whitespace errors in this artifact.
7. **`git diff --check` (whole tree) → exit 2, one pre-existing report:
   `.automation/tests/test_common.py:40: new blank line at EOF`.** That file was already modified
   before that slice and was outside its scope; it was not fixed and not reverted.
8. `git status --short` → only this file added by that task.
9. No runtime test, build or screenshot was run (documentation-only brief).

### 8.2 Fresh repair checks at HEAD `dd1abe1` (2026-09-14)

1. `git rev-parse HEAD` → `dd1abe143cec7b6bd9a1c90090b210b59b5fe0ba`.
   `git diff --name-only d42e71b dd1abe1` → only `.automation/*` files, so no client line reference
   in this document drifted between the two HEADs.
2. `git status --short` before and after the repair → the same three pre-existing modified files
   (`.automation/prompts/orchestrator_slice.md`, `.automation/scripts/supervisor.py`,
   `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`) plus this untracked artifact. Nothing else
   was touched by this repair.
3. Route/task resolver semantics executed against the real modules (Node 24 type-stripping; probe
   script `w0-01-r1-resolver-probe.mjs` in the runner temp directory, not added to the repository):
   - `portfolioTaskFromLocation("?workspace=orders")` → `overview`;
   - `portfolioTaskFromLocation("?workspace=orders&task=exposure")` → `exposure`;
   - `portfolioTaskFromLocation("?workspace=contracts&task=exposure")` → `exposure`;
   - `portfolioTaskToSearch("?workspace=orders&task=exposure", "exposure")` →
     `workspace=contracts&task=exposure`;
   - `decisionTaskFromLocation("?workspace=review")` → `review`;
     `decisionTaskFromLocation("?workspace=review&task=optimize")` → `review` (legacy branch wins);
   - `strategyTaskFromLocation("?workspace=strategy&task=orders")` → `design`;
   - `resolveMarketViewTask({search:"?task=network", activeWorkspace:"market", persisted:"curves"})`
     → `{"task":"network","source":"url"}`; with `search:""` and `persisted:"network"` →
     `{"task":"network","source":"persisted"}`.
   These are the values asserted in §2.4/§2.5/§4.3.
4. Reference/reachability script over `clients/web/src` (PowerShell `Select-String`, results):
   `StrategyShadowRunTerminal` appears only in its own file (`:34, 220, 235`);
   `StrategyShadowRunSections` only at `StrategyShadowRunTerminal.tsx:17, 24`;
   `StrategyShadowShell` at `StrategyLabWorkspace.tsx:8, 95` (mount) and in its own file;
   no `openWorkspace("orders")` call site and no `?workspace=orders` producer anywhere;
   shell interception `navigation.activeWorkspace === "network"` at `AppShell.tsx:167`;
   `context.result_mismatch` renders at `NetworkWorkspace.tsx:271-272`,
   `ScenarioWorkspace.tsx:77` and (unmounted) `StrategyShadowRunTerminal.tsx:632`;
   no consumer of `routeContextMismatch` / `strategyContextMismatch` outside the model.
5. Endpoint mapping re-check (same rule as 8.1): 107 distinct client path literals extracted from
   `clients/web/src/api/client.ts` (excluding the `/api` base constant) vs the pinned declaration
   block `tests/contract/test_api_surface_stability.py:15-179` (163 paths) → **0 unmatched** after
   normalising `${...}`/`{...}` segments to `{}`; the three `stream/*` literals
   (`/stream/quotes`, `/stream/opportunities`, `/stream/alerts`) live in
   `clients/web/src/stores/api.ts`.
6. Client method census re-check, rule: for each of the 117 methods declared in the `api` object
   (`clients/web/src/api/client.ts:1821-2158`), search `clients/web/src` (excluding that file) for a
   reference of the form `api.<name>`, `apiClient.<name>` or `client.api.<name>` → 91 referenced,
   26 without such a reference; the 26 names are the list in §4.7. (A looser bare-identifier search
   gives 96/21 because words such as `health`, `strategy` and `netback` also occur as unrelated
   property names; the call-site-shaped rule is the one this document uses.)
7. Citation audit (scripted, this repair; script kept in the runner temp directory as
   `w0-01-r1-citation-audit-final.ps1`): every `` `path:line(s)` `` reference was re-extracted and
   resolved - repository-relative path first, then the short-form convention above, then a bare
   filename only when it is unique in the repository - and each line spec was checked for bounds.
   Result at `dd1abe1`: **410 references checked, 409 resolved with in-range line numbers,
   1 documented wrong-path mention (the `clients/web/src/hooks/...` form quoted in the path
   convention as an error), 0 unresolved, 0 out of range.** A separate bare-name pass found
   47 short forms, 0 ambiguous.
   Three defects found by the audit were fixed in this repair: the identity-hook path (§1.2), the
   out-of-range `04_...:236-270` citation (§9) and the `StrategyShadowRunTerminal` length
   (845 lines, was stated as 810) plus its "unreferenced" claim (§2.8).
8. `git diff --check` (whole tree, repair state) → exit 0, no whitespace errors (the three modified
   files emit CRLF/LF conversion warnings only). `git diff --no-index --check -- /dev/null
   docs/engineering/Architecture-V2/W0-01_CLIENT_INVENTORY.md` → exit 1 with **no** whitespace
   diagnostics, i.e. the artifact itself is whitespace-clean; exit 1 is the normal `--no-index`
   "files differ" code, not a whitespace report.
9. Runtime tests: `node --test tests/productNavigation.test.ts tests/commercialWorkflow.test.ts
   tests/workspaceHeader.test.ts` was attempted from `clients/web` and the runner could not spawn
   child processes in this environment (`Error: spawn EPERM`). **No runtime test result is claimed**
   for this documentation-only repair; the resolver behaviour above was exercised directly instead.

## 9. Coverage limits and follow-up questions

Limits:

- Only the web/desktop client was inventoried. Backend routes, permissions, entitlements and
  provider/admin surfaces (planned W0-02) were not audited beyond the pinned-path cross-check.
- Endpoint verification proves a client path exists on the backend surface; it does not prove
  payload-shape compatibility or that the UI sends correct parameters. Backend authorization,
  entitlement enforcement and provider/licence behaviour were **not** inspected; §2.7 records only
  the UI gates that exist in the client.
- Line references are valid at HEAD `dd1abe1…` (unchanged from the original `d42e71b…` inspection
  for `clients/...` files); they will drift with later edits.
- Static reference search and user reachability are different claims. The "no call site" list
  (§4.7) and the component reference counts (§2.8) are static: an unreferenced method could still
  be reached through a dynamic path added later, and a referenced component (such as
  `StrategyShadowRunSections`) can still be unmounted. No runtime trace or coverage run was made.
- Visual/accessibility evidence was explicitly out of scope (`RFC-0001` acceptance gates remain
  open per Decision 14).

Follow-up questions for Astra (no answer asserted here):

1. Which current page ids become canonical "work modes" versus remaining routes, given
   `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md:161-187`?
2. Should `network` stay a shell-level special case, or move into the market shell contract in
   Wave 1 (`AppShell.tsx:166-226`)?
3. Is the client-held API token / operator principal (`clients/web/src/api/client.ts:6-8, 15-26,
   44-86`) inside Wave 2/3 scope, and does that require a security review before any change?
4. Are the map-tile third-party requests (§6.5) in scope for the Wave 4 provider/entitlement work,
   or for a separate licence review?
5. Are the 26 client methods without a call-site reference (§4.7) and the unmounted shadow-run
   terminal plus its referenced sections (§2.8) intended surfaces that Wave 7/9 must mount, or
   should they be retired? (Reachability, not just static reference, must be the deciding evidence.)
6. Does the auto-optimizer effect (R1) count as current accepted behaviour or as a defect to be
   fixed in Wave 5?
7. Should the portfolio task resolver gain a legacy branch so that `?workspace=orders` opens
   Market Positioning - i.e. treat it like the Decision workspace's `?workspace=review` mapping
   (`clients/web/src/app/model/commercialWorkflowModel.ts:19-28`) - or should the `orders` page id
   be retired from the deep-link contract? Today the two disagree (§2.4), and either resolution is
   an architecture decision for Astra, not a documentation fix.

## 10. Explicit non-changes

- No code, test, schema, migration, API, dependency, configuration, security, permission, release
  or UI behaviour change, in the original task or in this repair.
- This repair (W0-01-R1) changed only this document: corrections in §1.2, §2.3-§2.5, §2.7-§2.8,
  §4.3, §4.7, §6.3, §7-§9. No runtime, test, flow, entitlement or host file was edited.
- No ADR acceptance or supersession; Decision 14 and RFC-0001 remain as recorded.
- `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` was read but not modified.
- No secrets were read or printed; `DEEPSEEK_API_KEY` remains outside the repository.
- No commit, push or merge; no supervisor or additional worker was launched.
