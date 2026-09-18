import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { marketTaskFromLocation } from "../src/app/model/marketCockpitModel.ts";
import {
  decisionTaskFromLocation,
  portfolioTaskFromLocation,
} from "../src/app/model/commercialWorkflowModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("consolidated headers expose the primary workspace and actual task labels", () => {
  const market = readWebSource("components/MarketCockpit.tsx");
  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  const decision = readWebSource("components/DecisionWorkspace.tsx");

  assert.match(market, /title=\{t\("nav\.primary\.market"\)\}/);
  assert.match(market, /taskLabel=\{t\(`market\.task\.\$\{task\}`\)\}/);
  assert.match(portfolio, /title=\{t\("nav\.primary\.portfolio"\)\}/);
  assert.match(portfolio, /taskLabel=\{t\(`portfolio\.task\.\$\{task\}`\)\}/);
  assert.match(decision, /title=\{t\("nav\.primary\.decision"\)\}/);
  assert.match(decision, /taskLabel=\{t\(`decision\.task\.\$\{task\}`\)\}/);
});

test("initial, deep-link, and history task locations resolve the labels used by headers", () => {
  // The market primary lands on the numeric view; `overview` needs `?task=`.
  assert.equal(marketTaskFromLocation("", "market"), "curves");
  assert.equal(marketTaskFromLocation("?workspace=market", "market"), "curves");
  assert.equal(marketTaskFromLocation("?workspace=market&task=overview", "market"), "overview");
  assert.equal(marketTaskFromLocation("?workspace=market&task=network", "market"), "network");
  assert.equal(marketTaskFromLocation("?workspace=network", "network"), "network");
  assert.equal(portfolioTaskFromLocation(""), "overview");
  assert.equal(portfolioTaskFromLocation("?workspace=contracts&task=exposure"), "exposure");
  assert.equal(decisionTaskFromLocation("?workspace=scenario&task=optimize"), "optimize");
  assert.equal(decisionTaskFromLocation("?workspace=review&task=review"), "review");
});

test("only WorkspaceHeader owns the consolidated primary h1 and shared tab semantics remain delegated", () => {
  const header = readWebSource("components/ui/WorkspaceHeader.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  // One top-level heading per header, and one section heading for the local-tabs pages: exactly
  // one branch of each level, so a page can have a single h1 whichever header owns it.
  assert.equal((header.match(/<h1>\{title\}<\/h1>/g) ?? []).length, 1);
  assert.equal((header.match(/<h2>\{title\}<\/h2>/g) ?? []).length, 1);
  assert.match(header, /<WorkspaceTabs/);
  assert.match(header, /idPrefix=\{idPrefix\}/);
  assert.match(header, /panelId=\{panelId\}/);
  assert.match(renderer, /usesConsolidatedHeader/);
  assert.match(renderer, /!usesConsolidatedHeader/);
  assert.match(renderer, /!usesConsolidatedHeader\s*&&\s*\(\s*<header/);
});

test("a page has one h1, and the registry decides which header owns it", () => {
  // A `local-tabs` page's heading belongs to the shell, so a workspace that renders a header of
  // its own there is a *section* under it. Three surfaces (strategy, research, agents) were given
  // their own header by Wave 9 while their pages stayed `local-tabs`, and each rendered a second
  // `<h1>` beside the shell's - invisible to every source-text test and only found by the
  // whole-product browser sweep, which counts h1s per rendered page.
  const registry = readWebSource("app/experience/workspacePatterns.ts");
  assert.match(
    registry,
    /export function workspaceHeaderTitleLevel\(page: WorkspacePageId\): 1 \| 2 \{\s*return headerModeForPage\(page\) === "local-tabs" \? 2 : 1;/s,
  );

  for (const [file, page] of [
    ["components/strategy/StrategyLabWorkspace.tsx", "strategy"],
    ["components/ResearchDataWorkspace.tsx", "research"],
    ["components/AgentsWorkspace.tsx", "agents"],
  ] as const) {
    assert.match(
      readWebSource(file),
      new RegExp(`titleLevel=\\{workspaceHeaderTitleLevel\\("${page}"\\)\\}`),
      file,
    );
  }
});

test("the direct map-first Network route is composed, not intercepted", () => {
  const shell = readWebSource("app/shell/AppShell.tsx");
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  const model = readWebSource("app/model/marketCockpitModel.ts");

  // Conflicting register C9: the shell used to mount its own page-level heading and the
  // network surface for this route. It now composes every page through the workspace
  // renderer, and the market primary owns the page's single heading through
  // WorkspaceHeader, which is the only component that renders an <h1> for a page.
  assert.equal(shell.includes('activeWorkspace === "network"'), false);
  assert.equal(shell.includes("network-main-title"), false);
  assert.match(shell, /<WorkspaceRenderer controller=\{controller\} \/>/);

  // The route still lands on the map: the task resolves from the page id itself, so no
  // URL change is needed for the map-first entry to keep working.
  assert.match(model, /if \(activeWorkspace === "network"\) return "network";/);
  assert.match(cockpit, /\{task === "network" && \(/);

  // The hand-off the shell used to own moved with the mount, so the route carried into
  // the scenario workspace is unchanged.
  assert.match(cockpit, /const routeId =\s*portfolio\.selectedAllocation\?\.route_id \?\?/s);
  assert.match(cockpit, /if \(routeId\) selection\.setRouteId\(routeId\);/);
});

test("the narrow alert trigger keeps a visible text label", () => {
  const alertCenter = readWebSource("components/AlertCenter.tsx");
  const css = readWebSource("components/WorkspaceTopBar.css");

  assert.match(alertCenter, /<span>\{isChinese \? "告警" : "Alerts"\}<\/span>/);
  assert.equal(css.includes(".alert-trigger span:not(.alert-trigger-mark)"), false);
});

test("the header preferences menu owns preference and lifecycle actions with keyboard return", () => {
  const menu = readWebSource("components/HeaderPreferencesMenu.tsx");
  const bar = readWebSource("components/WorkspaceTopBar.tsx");

  assert.match(bar, /<HeaderPreferencesMenu/);
  assert.match(menu, /aria-haspopup="menu"/);
  assert.match(menu, /role="menu"/);
  assert.match(menu, /role="menuitemradio"/);
  assert.match(menu, /role="menuitem"/);
  assert.match(menu, /event\.key === "Escape"/);
  assert.match(menu, /event\.key === "ArrowDown"/);
  assert.match(menu, /event\.key === "ArrowUp"/);
  assert.match(menu, /triggerRef\.current\?\.focus\(\)/);
  assert.match(menu, /requestAnimationFrame\(\(\) => triggerRef\.current\?\.focus\(\)\)/);
  assert.match(menu, /onLanguageChange\("en"\)/);
  assert.match(menu, /onLanguageChange\("zh-CN"\)/);
  assert.match(menu, /onModeChange\(themeMode\)/);
  assert.match(menu, /onOpenSettings/);
  assert.match(menu, /onSignOut/);
});

test("the narrow header collapses context and status behind one disclosure", () => {
  const bar = readWebSource("components/WorkspaceTopBar.tsx");
  const css = readWebSource("styles/app.css");

  assert.match(bar, /matchMedia\("\(max-width: 900px\)"\)/);
  assert.match(bar, /className="topbar-context-disclosure"/);
  assert.match(bar, /<summary aria-label=\{t\("topbar\.context_status"\)\}>/);
  assert.match(bar, /\(!narrowHeader \|\| contextDisclosureOpen\)/);
  assert.match(css, /grid-template-areas: "workspace" "context-disclosure";/);
  assert.match(css, /grid-template-areas: "workspace" "task" "search" "context-disclosure";/);
  assert.match(css, /\.topbar-context-disclosure-content[\s\S]*?display: grid;/);
});

test("the top bar identity cluster keeps the display name and role apart", () => {
  const bar = readWebSource("components/WorkspaceTopBar.tsx");
  const css = readWebSource("components/WorkspaceTopBar.css");

  // The markup wraps the display name and the role in one container and JSX
  // drops the whitespace between them, so a missing container rule rendered
  // them as a single glued token ("dev.analystANALYST") in every locale and at
  // every width. A visual review caught it; axe cannot see missing whitespace.
  assert.match(bar, /className="topbar-user-menu"/);

  const container = /\.topbar-user-menu \{[^}]*\}/.exec(css)?.[0] ?? "";
  assert.notEqual(container, "", "the class the markup uses must have a rule");
  assert.match(container, /display: flex;/);
  assert.match(container, /gap: 8px;/);

  // The name is the only flexible field, so a long one ellipsises rather than
  // pushing the sign-out control out of the row.
  const name = /\.topbar-user-menu > span \{[^}]*\}/.exec(css)?.[0] ?? "";
  assert.match(name, /text-overflow: ellipsis;/);
  assert.match(name, /white-space: nowrap;/);
  const role = /\.topbar-user-menu > small \{[^}]*\}/.exec(css)?.[0] ?? "";
  assert.match(role, /white-space: nowrap;/);
});

