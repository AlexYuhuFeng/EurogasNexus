/**
 * Architecture V2 Wave 9 - shell surfaces: the canonical Inspector and the
 * command palette.
 *
 * These tests pin the parts that can silently rot: the palette derives its
 * commands from the navigation/AI/utility registries instead of a hand-written
 * list, unavailable commands are explained rather than hidden, the Inspector
 * renders a selection instead of fetching its own detail, and both surfaces are
 * keyboard reachable and labelled.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  DEFAULT_PALETTE_LIMIT,
  EMPTY_INSPECTOR_STATE,
  aiCommands,
  buildPaletteCommands,
  filterPaletteCommands,
  inspectionCommands,
  inspectorReducer,
  isPaletteDismissKey,
  isPaletteShortcut,
  navigationCommands,
  openInspector,
  paletteCommandAvailable,
  paletteUnavailableReasonKey,
  shellRegionContract,
  utilityCommands,
} from "../src/app/experience/index.ts";
import { primaryWorkspaces } from "../src/app/navigation/productNavigation.ts";
import { workspacePageIds } from "../src/workspaceNavigation.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("the inspector region is rendered, not merely declared", () => {
  const contract = shellRegionContract("inspector");
  assert.equal(contract.implementation, "present");
  assert.equal(contract.markupMarker, "inspector");

  const panel = readWebSource("components/InspectorPanel.tsx");
  const shell = readWebSource("app/shell/AppShell.tsx");

  assert.match(panel, /data-shell-region="inspector"/);
  assert.match(panel, /aria-label=\{t\("experience\.inspector\.title"\)\}/);
  assert.match(panel, /<dl className="inspector-panel-facts">/);
  assert.match(shell, /inspector\.subject && \(\s*<InspectorPanel/);

  // The Inspector renders the selection it is given: it does not fetch, and it
  // therefore cannot become a second entitlement path.
  for (const banned of ["useApiStore", "fetch(", "api.", "useEffect", "localStorage"]) {
    assert.equal(panel.includes(banned), false, banned);
  }
  assert.equal((panel.match(/<h2>/g) ?? []).length, 1);
});

test("palette commands are derived from the registries", () => {
  const commands = buildPaletteCommands();
  const ids = commands.map((command) => command.id);
  assert.equal(new Set(ids).size, ids.length);

  assert.deepEqual(
    navigationCommands()
      .filter((command) => command.target.primary)
      .map((command) => command.target.primary),
    primaryWorkspaces.map((primary) => primary.id),
  );
  assert.deepEqual(
    navigationCommands()
      .filter((command) => command.target.page && !command.target.primary)
      .map((command) => command.target.page),
    workspacePageIds,
  );
  assert.deepEqual(
    aiCommands().map((command) => command.target.aiAction),
    ["ask", "explain", "compare", "challenge", "draft"],
  );
  assert.deepEqual(
    utilityCommands().map((command) => command.target.utility),
    ["access-identity", "sign-out"],
  );
});

test("inspection commands follow the active context", () => {
  const empty = inspectionCommands({}, "network");
  assert.deepEqual(empty, []);

  const withRoute = inspectionCommands({ routeId: "ROUTE-9" }, "network");
  assert.deepEqual(
    withRoute.map((command) => command.target.inspector),
    ["route"],
  );
  assert.equal(withRoute[0]?.placement, "inspector");
  assert.equal(withRoute[0]?.consequence, "read");

  const full = inspectionCommands(
    {
      routeId: "R",
      resourceId: "P",
      strategyVersionId: "V",
      strategyRunId: "X",
    },
    "strategy",
  );
  assert.deepEqual(
    full.map((command) => command.target.inspector),
    ["route", "resource", "strategy-version", "strategy-run"],
  );
  for (const command of full) assert.equal(command.target.page, "strategy");

  // Navigation, inspection and utility labels must exist in a command id space
  // that cannot collide.
  const ids = buildPaletteCommands()
    .map((command) => command.id)
    .concat(full.map((command) => command.id));
  assert.equal(new Set(ids).size, ids.length);
});

test("availability is explained, never silently hidden", () => {
  const [ask] = aiCommands();
  const accessIdentity = utilityCommands().find(
    (command) => command.target.utility === "access-identity",
  );
  const marketNavigation = navigationCommands().find(
    (command) => command.target.page === "market",
  );
  assert.ok(ask && accessIdentity && marketNavigation);

  const analyst = { capabilities: ["research.query"], activeContextComplete: true };
  assert.equal(paletteCommandAvailable(ask, analyst), true);
  assert.equal(paletteCommandAvailable(ask, { ...analyst, activeContextComplete: false }), false);
  assert.equal(
    paletteUnavailableReasonKey(ask, { ...analyst, activeContextComplete: false }),
    "experience.palette.unavailable_context",
  );
  assert.equal(
    paletteUnavailableReasonKey(ask, { capabilities: [], activeContextComplete: true }),
    "experience.palette.unavailable_capability",
  );

  // Navigation is never gated by the client; the backend authorises it.
  assert.equal(paletteCommandAvailable(marketNavigation, { capabilities: [], activeContextComplete: false }), true);
  assert.equal(paletteUnavailableReasonKey(marketNavigation, { capabilities: [], activeContextComplete: false }), null);

  // Reaching the access surface needs an administration capability.
  assert.equal(paletteCommandAvailable(accessIdentity, { capabilities: [], activeContextComplete: true }), false);
  assert.equal(
    paletteCommandAvailable(accessIdentity, { capabilities: ["access.manage"], activeContextComplete: true }),
    true,
  );
});

test("the palette controller keeps the contract's keyboard and ranking model", () => {
  const hook = readWebSource("app/hooks/useCommandPalette.ts");
  const component = readWebSource("components/CommandPalette.tsx");

  assert.match(hook, /isPaletteShortcut\(event\)/);
  assert.match(hook, /isPaletteDismissKey\(event\)/);
  assert.match(hook, /filterPaletteCommands\(/);
  assert.match(hook, /inspectionCommands\(options\.context, options\.activeWorkspace\)/);
  // AI commands stay out of the runtime palette until their invocation surface
  // exists (Wave 7), so no command is offered that does nothing when chosen.
  assert.match(hook, /options\.includeAiActions === true && command\.group === "ai"/);

  assert.match(component, /role="dialog"/);
  assert.match(component, /aria-modal="true"/);
  assert.match(component, /role="listbox"/);
  assert.match(component, /role="option"/);
  assert.match(component, /aria-disabled=\{disabled\}/);
  assert.match(component, /onKeyDown=\{\(event\) => \{/);
  assert.match(component, /event\.key === "ArrowDown"/);
  assert.match(component, /event\.key === "Enter"/);
  assert.match(component, /event\.key === "Escape"/);
  assert.equal(component.includes("dangerouslySetInnerHTML"), false);

  // The shell mounts both surfaces and owns the shortcut binding.
  const shell = readWebSource("app/shell/AppShell.tsx");
  assert.match(shell, /useCommandPalette\(\{/);
  assert.match(shell, /<CommandPalette/);
  assert.match(shell, /useInspectorStore\(\)/);
});

test("inspector selection state follows the pure reducer", () => {
  let state = EMPTY_INSPECTOR_STATE;
  state = inspectorReducer(
    state,
    openInspector({ kind: "route", ref: "R-1", label: "North route", originPage: "network" }),
  );
  assert.equal(state.subject?.ref, "R-1");
  const store = readWebSource("stores/inspector.ts");
  assert.match(store, /inspectorReducer\(/);
  assert.match(store, /create<InspectorStore>\(/);
  assert.match(store, /subject: null, history: \[\]/);
});

test("palette and inspector vocabulary is bilingual and bounded", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = [
    "experience.inspector.title",
    "experience.inspector.back",
    "experience.inspector.close",
    "experience.inspector.ref",
    "experience.inspector.origin",
    "experience.inspector.note",
    "experience.inspect.route",
    "experience.inspect.resource",
    "experience.inspect.strategy-version",
    "experience.inspect.strategy-run",
    "experience.palette.title",
    "experience.palette.placeholder",
    "experience.palette.empty",
    "experience.palette.group.navigate",
    "experience.palette.group.inspect",
    "experience.palette.group.ai",
    "experience.palette.group.utility",
    "experience.palette.unavailable_capability",
    "experience.palette.unavailable_context",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    // "AI" is the same word in both locales; every other label must be translated.
    if (key !== "experience.palette.group.ai") assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);

  // The default result window stays a bounded, readable list.
  assert.equal(DEFAULT_PALETTE_LIMIT, 8);
  assert.equal(filterPaletteCommands(buildPaletteCommands(), "", (command) => command.labelKey).length, DEFAULT_PALETTE_LIMIT);
  assert.equal(isPaletteShortcut({ key: "k", metaKey: true }), true);
  assert.equal(isPaletteDismissKey({ key: "Escape" }), true);
});
