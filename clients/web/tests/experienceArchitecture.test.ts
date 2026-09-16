/**
 * Architecture V2 Wave 1 - Product Experience Architecture contract tests.
 *
 * These tests keep the machine-readable experience contract and the running client in
 * agreement. They are deliberately about *claims*: a region, pattern, panel, action or
 * capability that the contract declares must either exist in the source or be marked
 * as planned, and the composition the renderer uses must come from the registry
 * rather than from a second local list.
 */

import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import test from "node:test";

import {
  ACTIVE_CONTEXT_GAPS,
  ACTIVE_CONTEXT_QUERY_KEYS,
  AI_ACTION_KINDS,
  AI_INVARIANTS,
  ACTION_CONSEQUENCES,
  ACTION_PLACEMENTS,
  DEFAULT_PALETTE_LIMIT,
  EMPTY_INSPECTOR_STATE,
  INSPECTOR_SUBJECT_KINDS,
  PANEL_KINDS,
  SHELL_REGIONS,
  WORKSPACE_PATTERNS,
  WORK_MODE_GRANTS_AUTHORITY,
  WORK_MODE_IDS,
  actionGeography,
  actionPlacement,
  activeContextFromParts,
  activeContextGapOwner,
  activeContextIsReproducible,
  activeContextKey,
  aiActionContract,
  aiActionIsAvailable,
  aiCommands,
  buildPaletteCommands,
  canOpenInspector,
  compositionForPage,
  filterPaletteCommands,
  headerModeForPage,
  inspectorReducer,
  isPaletteDismissKey,
  isPaletteShortcut,
  mayOccupyPrimarySlot,
  navigationCommands,
  openInspector,
  panelContract,
  panelTaxonomy,
  plannedShellRegions,
  registeredPages,
  renderedShellRegions,
  requiredDisclosures,
  requiresDeliberateStep,
  shellRegionContract,
  shellRegions,
  taskPatternFor,
  taskPatterns,
  usesConsolidatedHeader,
  utilityCommands,
  workModeComposition,
  workModes,
  workspaceCompositions,
} from "../src/app/experience/index.ts";
import {
  HOST_COMMANDS,
  HOST_COMMAND_CAPABILITIES,
  hostCapabilities,
  hostCommandCapability,
  hostSupportsCommand,
  isHostCommand,
  resolveHostKind,
  requireHostCommand,
  tryHostCommand,
} from "../src/app/host/hostCapabilities.ts";
import { workspacePageIds } from "../src/workspaceNavigation.ts";
import {
  primaryWorkspaces,
  primaryWorkspaceForPage,
} from "../src/app/navigation/productNavigation.ts";
import {
  decisionTaskFromLocation,
  portfolioTaskFromLocation,
} from "../src/app/model/commercialWorkflowModel.ts";
import { marketTaskFromLocation } from "../src/app/model/marketCockpitModel.ts";

const WEB_ROOT = new URL("../", import.meta.url);

/** Resolve a repository-relative path (the form the contract documents use). */
function repoFile(relativePath: string): URL {
  return new URL(`../../../${relativePath}`, import.meta.url);
}

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readJson(relativePath: string): Record<string, string> {
  return JSON.parse(readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8")) as Record<
    string,
    string
  >;
}

function sourceFiles(relativeDirectory = ""): string[] {
  const directory = new URL(`../src/${relativeDirectory}`, import.meta.url);
  const files: string[] = [];
  for (const entry of readdirSync(directory)) {
    const relative = relativeDirectory ? `${relativeDirectory}/${entry}` : entry;
    if (statSync(new URL(`../src/${relative}`, import.meta.url)).isDirectory()) {
      files.push(...sourceFiles(relative));
    } else if (/\.tsx?$/.test(entry)) {
      files.push(relative);
    }
  }
  return files;
}

test("the experience vocabulary is unique, guarded and fully labelled", () => {
  for (const list of [SHELL_REGIONS, WORKSPACE_PATTERNS, PANEL_KINDS, ACTION_PLACEMENTS, AI_ACTION_KINDS, INSPECTOR_SUBJECT_KINDS]) {
    assert.equal(new Set(list).size, list.length, "vocabulary entries must be unique");
    assert.ok(list.length > 0);
  }

  const en = readJson("i18n/en.json");
  const zh = readJson("i18n/zh.json");
  const labelKeys = [
    ...SHELL_REGIONS.map((region) => `experience.region.${region}`),
    ...WORKSPACE_PATTERNS.map((pattern) => `experience.pattern.${pattern.toLowerCase()}`),
    ...PANEL_KINDS.map((kind) => `experience.panel.${kind}`),
    ...AI_ACTION_KINDS.map((action) => `experience.ai.${action}`),
  ];
  for (const key of labelKeys) {
    assert.ok(key in en, `en is missing ${key}`);
    assert.ok(key in zh, `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});

test("every declared shell region has a contract and the markup tells the truth", () => {
  assert.deepEqual(
    shellRegions.map((contract) => contract.region).sort(),
    [...SHELL_REGIONS].sort(),
  );

  const shell = readWebSource("app/shell/AppShell.tsx");
  const topBar = readWebSource("components/WorkspaceTopBar.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");
  const combined = shell + topBar + renderer;

  // A "present" region must actually be marked in the rendered shell; a "planned"
  // one must not pretend to be.
  for (const region of renderedShellRegions()) {
    const marker = shellRegionContract(region).markupMarker;
    assert.ok(marker, `${region} claims rendered markup but declares no marker`);
    assert.ok(
      combined.includes(`data-shell-region="${marker}"`) ||
        combined.includes(`shellRegion="${marker}"`),
      `${region} declares markup marker '${marker}' that no shell component renders`,
    );
  }
  assert.deepEqual(plannedShellRegions(), ["inspector"]);
  assert.equal(combined.includes('data-shell-region="inspector"'), false);
});

test("the workspace-pattern registry covers every page exactly once and owns one primary", () => {
  assert.equal(workspaceCompositions.length, workspacePageIds.length);
  assert.deepEqual([...registeredPages()].sort(), [...workspacePageIds].sort());

  for (const page of workspacePageIds) {
    const composition = compositionForPage(page);
    assert.equal(composition.primary, primaryWorkspaceForPage(page).id, page);
    assert.ok(WORKSPACE_PATTERNS.includes(composition.pattern), page);
    for (const kind of composition.inspectorSubjects) {
      assert.ok(INSPECTOR_SUBJECT_KINDS.includes(kind), `${page}: ${kind}`);
    }
    for (const panel of composition.panels) {
      assert.ok(PANEL_KINDS.includes(panel), `${page}: ${panel}`);
    }
    // Every inspector subject a surface declares must be openable on that surface.
    for (const kind of composition.inspectorSubjects) {
      assert.ok(canOpenInspector(kind, page), `${page} declares ${kind} but refuses to open it`);
    }
  }
});

test("header composition is read from the registry, not from a local primary list", () => {
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  assert.match(
    renderer,
    /import \{ headerModeForPage \} from "@\/app\/experience\/workspacePatterns"/,
  );
  assert.match(
    renderer,
    /const usesConsolidatedHeader = headerModeForPage\(activeWorkspace\) === "consolidated";/,
  );
  assert.equal(renderer.includes('["market", "portfolio", "decision"].includes'), false);

  // The registry must reproduce the composition the client renders today.
  const consolidated = primaryWorkspaces
    .filter((primary) => primary.pages.some((page) => usesConsolidatedHeader(page)))
    .map((primary) => primary.id);
  assert.deepEqual(consolidated.sort(), ["decision", "market", "portfolio"]);
  for (const primary of primaryWorkspaces) {
    const modes = new Set(primary.pages.map((page) => headerModeForPage(page)));
    assert.equal(modes.size, 1, `${primary.id} mixes header modes across its pages`);
  }
});

test("task patterns cover the vocabularies the live resolvers can return", () => {
  // Live resolver values, not a copied list: a resolver change breaks this test.
  const marketTasks = new Set(
    ["", "?workspace=market", "?task=overview", "?task=network", "?task=capacity"].map((search) =>
      marketTaskFromLocation(search, "market"),
    ),
  );
  for (const task of marketTasks) assert.doesNotThrow(() => taskPatternFor("market", task));

  const portfolioTasks = new Set(
    ["", "?task=resources", "?task=routes", "?task=exposure"].map(portfolioTaskFromLocation),
  );
  for (const task of portfolioTasks) assert.doesNotThrow(() => taskPatternFor("portfolio", task));

  const decisionTasks = new Set(
    ["", "?workspace=review", "?task=optimize"].map(decisionTaskFromLocation),
  );
  for (const task of decisionTasks) assert.doesNotThrow(() => taskPatternFor("decision", task));

  for (const task of ["design", "backtest", "compare", "shadow"]) {
    assert.doesNotThrow(() => taskPatternFor("strategy", task));
  }
  // The system primary keeps local views until Wave 9 and claims no task pattern.
  assert.deepEqual(taskPatterns.system, {});
});

test("panel taxonomy owners exist and every composition uses declared panels", () => {
  for (const contract of panelTaxonomy) {
    assert.ok(contract.purpose.length > 0, contract.kind);
    assert.ok(contract.patterns.length > 0, contract.kind);
    for (const owner of contract.owners) {
      assert.ok(existsSync(repoFile(owner)), `${contract.kind}: ${owner}`);
    }
    if (contract.implementation === "present") {
      assert.ok(contract.owners.length > 0, `${contract.kind} claims present without an owner`);
    }
  }

  for (const page of workspacePageIds) {
    const panels = compositionForPage(page).panels;
    assert.ok(panels.length > 0, page);
    assert.ok(requiredDisclosures(panels).length > 0, `${page} owes no disclosure`);
  }
  // Material value panels must carry a time basis and units.
  for (const kind of ["metric-strip", "time-series", "run-result"] as const) {
    const disclosures = panelContract(kind).disclosures;
    assert.ok(disclosures.includes("as-of"), kind);
  }
});

test("action geography places every consequence once, without granting authority", () => {
  assert.deepEqual(
    actionGeography.map((rule) => rule.consequence).sort(),
    [...ACTION_CONSEQUENCES].sort(),
  );
  for (const rule of actionGeography) {
    assert.ok(ACTION_PLACEMENTS.includes(rule.placement), rule.consequence);
    assert.ok(rule.rationale.length > 20, rule.consequence);
  }

  assert.equal(actionPlacement("compute"), "workspace-primary");
  assert.equal(actionPlacement("persist"), "workspace-primary");
  assert.equal(actionPlacement("read"), "surface-local");
  assert.equal(actionPlacement("export"), "workspace-secondary");
  assert.equal(actionPlacement("lifecycle"), "object-overflow");
  assert.equal(actionPlacement("destructive"), "object-overflow");
  assert.equal(actionPlacement("utility"), "shell-utility");

  assert.equal(mayOccupyPrimarySlot("compute"), true);
  assert.equal(mayOccupyPrimarySlot("destructive"), false);
  assert.equal(requiresDeliberateStep("destructive"), true);
  assert.equal(requiresDeliberateStep("read"), false);
});

test("canonical AI actions keep the deterministic and entitlement boundary", () => {
  assert.deepEqual(
    AI_ACTION_KINDS.map((action) => aiActionContract(action).action),
    [...AI_ACTION_KINDS],
  );

  assert.equal(AI_INVARIANTS.deterministicEnginesOwnNumbers, true);
  assert.equal(AI_INVARIANTS.inheritsUserAuthority, true);
  assert.equal(AI_INVARIANTS.mayBypassEntitlement, false);
  assert.equal(AI_INVARIANTS.mayInventMissingData, false);
  assert.equal(AI_INVARIANTS.mayExecuteOrNominate, false);
  assert.equal(AI_INVARIANTS.storesHiddenReasoning, false);
  assert.equal(AI_INVARIANTS.requiresReauthorisationPerCall, true);

  // No AI action may be offered without context and at least one evidence reference.
  for (const action of AI_ACTION_KINDS) {
    assert.equal(
      aiActionIsAvailable(action, { activeContextComplete: false, evidenceRefCount: 3 }),
      false,
      action,
    );
    assert.equal(
      aiActionIsAvailable(action, { activeContextComplete: true, evidenceRefCount: 0 }),
      false,
      action,
    );
    assert.equal(
      aiActionIsAvailable(action, { activeContextComplete: true, evidenceRefCount: 1 }),
      true,
      action,
    );
  }

  for (const contract of ["interpret-only", "evidence-backed-draft", "evidence-backed-review"]) {
    assert.ok(
      AI_ACTION_KINDS.some((action) => aiActionContract(action).posture === contract),
      contract,
    );
  }
});

test("the Inspector is a pure state machine with a bounded history", () => {
  let state = EMPTY_INSPECTOR_STATE;
  assert.equal(state.subject, null);

  state = inspectorReducer(state, openInspector({
    kind: "route",
    ref: "ROUTE-1",
    label: "Route 1",
    originPage: "network",
  }));
  assert.equal(state.subject?.ref, "ROUTE-1");

  state = inspectorReducer(state, openInspector({
    kind: "capacity",
    ref: "CAP-9",
    label: "Capacity 9",
    originPage: "capacity",
  }));
  assert.equal(state.subject?.ref, "CAP-9");
  assert.equal(state.history.length, 1);

  state = inspectorReducer(state, { type: "back" });
  assert.equal(state.subject?.ref, "ROUTE-1");
  assert.equal(state.history.length, 0);

  // An empty reference is not a subject and must not open the panel.
  const unchanged = inspectorReducer(state, openInspector({
    kind: "route",
    ref: "",
    label: "empty",
    originPage: "network",
  }));
  assert.deepEqual(unchanged, state);

  state = inspectorReducer(state, { type: "close" });
  assert.equal(state.subject, null);
  state = inspectorReducer(state, { type: "reset" });
  assert.deepEqual(state, EMPTY_INSPECTOR_STATE);

  assert.equal(canOpenInspector("route", "network"), true);
  assert.equal(canOpenInspector("route", "settings"), false);
});

test("Active Context is canonical, keyed and honest about its gaps", () => {
  const context = activeContextFromParts({
    workspace: "network",
    trader: { gasDay: "2026-09-14", deliveryProduct: "day-ahead", hubId: "NBP" },
    selection: {
      routeId: "ROUTE-1",
      resourceId: null,
      strategyId: null,
      strategyVersionId: null,
      strategyRunId: null,
    },
  });

  assert.equal(context.gasDay, "2026-09-14");
  assert.equal(activeContextKey(context).startsWith("network|2026-09-14|day-ahead|NBP"), true);

  // Selecting a different object changes the key; the same context is stable.
  const same = activeContextFromParts({
    workspace: "network",
    trader: { gasDay: "2026-09-14", deliveryProduct: "day-ahead", hubId: "NBP" },
    selection: {
      routeId: "ROUTE-1",
      resourceId: null,
      strategyId: null,
      strategyVersionId: null,
      strategyRunId: null,
    },
  });
  assert.equal(activeContextKey(same), activeContextKey(context));

  assert.deepEqual(ACTIVE_CONTEXT_GAPS, ["organization", "portfolio", "decision-case", "analysis-snapshot"]);
  for (const gap of ACTIVE_CONTEXT_GAPS) assert.ok(activeContextGapOwner(gap).startsWith("Wave"));
  // Results are not reproducible until the Analysis Snapshot exists; the product
  // must not imply otherwise.
  assert.equal(activeContextIsReproducible(), false);
  assert.equal(activeContextIsReproducible(["organization", "portfolio"]), true);

  const params = new URLSearchParams(
    "?workspace=network&task=exposure&gasDay=2026-09-14&product=day-ahead&hub=NBP&route=ROUTE-1",
  );
  for (const key of Object.values(ACTIVE_CONTEXT_QUERY_KEYS)) {
    if (key === "resource" || key === "run" || key === "strategy" || key === "version") continue;
    assert.ok(params.has(key), key);
  }
});

test("work modes change composition only", () => {
  assert.equal(WORK_MODE_GRANTS_AUTHORITY, false);
  assert.equal(workModes.length, 5);
  assert.deepEqual([...WORK_MODE_IDS], workModes.map((mode) => mode.id));

  const en = readJson("i18n/en.json");
  const zh = readJson("i18n/zh.json");
  const primaryIds = primaryWorkspaces.map((primary) => primary.id);

  for (const mode of workModes) {
    assert.ok(en[mode.labelKey] && zh[mode.labelKey], mode.id);
    assert.ok(mode.emphasis.length > 0, mode.id);
    for (const primary of mode.emphasis) assert.ok(primaryIds.includes(primary), mode.id);
    assert.ok(mode.question.length > 20, mode.id);
    assert.ok(existsSync(repoFile(mode.canonicalSpec)), `${mode.id} points at a missing canonical spec`);
  }

  assert.equal(workModeComposition("trading-analysis").defaultPattern, "MONITOR");
  assert.equal(workModeComposition("administration").defaultPattern, "CONFIGURE");
});

test("the command palette is derived from the navigation, AI and utility registries", () => {
  const commands = buildPaletteCommands();
  const ids = commands.map((command) => command.id);
  assert.equal(new Set(ids).size, ids.length, "command ids must be unique");

  const navigation = navigationCommands();
  assert.deepEqual(
    navigation.filter((command) => command.target.primary).map((command) => command.target.primary),
    primaryWorkspaces.map((primary) => primary.id),
  );
  assert.deepEqual(
    navigation.filter((command) => command.target.page && !command.target.primary).map((command) => command.target.page),
    workspacePageIds,
  );
  assert.deepEqual(
    aiCommands().map((command) => command.target.aiAction),
    [...AI_ACTION_KINDS],
  );
  assert.deepEqual(
    utilityCommands().map((command) => command.id),
    ["utility.access-identity", "utility.sign-out"],
  );

  const en = readJson("i18n/en.json");
  const zh = readJson("i18n/zh.json");
  for (const command of commands) {
    assert.ok(en[command.labelKey], command.labelKey);
    assert.ok(zh[command.labelKey], command.labelKey);
  }

  // Ranking: prefix matches first, then substrings, bounded by the limit.
  const fixture = [
    { id: "a", label: "Market curves" },
    { id: "b", label: "Curves" },
    { id: "c", label: "Portfolio" },
  ] as const;
  const ranked = filterPaletteCommands(
    fixture.map((item) => ({
      id: item.id,
      group: "navigate" as const,
      labelKey: item.label,
      consequence: "read" as const,
      placement: "surface-local" as const,
      target: {},
    })),
    "cur",
    (command) => command.labelKey,
  );
  assert.deepEqual(ranked.map((command) => command.id), ["b", "a"]);
  const labelFor = (command: { labelKey: string }) => command.labelKey;
  assert.equal(filterPaletteCommands(commands, "zzzz", labelFor).length, 0);
  assert.equal(filterPaletteCommands(commands, "", labelFor).length, DEFAULT_PALETTE_LIMIT);
  assert.equal(commands.filter((c) => c.id.includes("market")).length > 0, true);

  assert.equal(isPaletteShortcut({ key: "k", ctrlKey: true }), true);
  assert.equal(isPaletteShortcut({ key: "K", metaKey: true }), true);
  assert.equal(isPaletteShortcut({ key: "k" }), false);
  assert.equal(isPaletteShortcut({ key: "k", ctrlKey: true, shiftKey: true }), false);
  assert.equal(isPaletteDismissKey({ key: "Escape" }), true);
  assert.equal(isPaletteDismissKey({ key: "Enter" }), false);
});

test("HostCapabilities is the single owner of the native boundary", () => {
  assert.equal(resolveHostKind({}), "browser");
  assert.equal(resolveHostKind({ protocol: "https:", hostname: "nexus.example" }), "browser");
  assert.equal(resolveHostKind({ hasTauriInternals: true }), "desktop");
  assert.equal(resolveHostKind({ protocol: "tauri:" }), "desktop");
  assert.equal(resolveHostKind({ hostname: "tauri.localhost" }), "desktop");

  const browser = hostCapabilities("browser");
  const desktop = hostCapabilities("desktop");
  assert.equal(browser.kind, "browser");
  assert.equal(desktop.kind, "desktop");
  for (const capability of Object.keys(browser) as Array<keyof typeof browser>) {
    if (capability === "kind") continue;
    assert.equal(browser[capability], false, String(capability));
    assert.equal(desktop[capability], true, String(capability));
  }

  // Only allowlisted commands may cross the boundary, and the client must not name
  // a native command that is not allowlisted.
  assert.equal(isHostCommand("notify_client_ready"), true);
  assert.equal(isHostCommand("rm -rf"), false);
  assert.equal(isHostCommand("eval"), false);

  // Every command carries a declared capability class, and a browser exposes none of
  // them: a bounded command list is not the same as "commands stay within
  // HostCapabilities" until each command is classified (W0-03 gap FF6-G1).
  const commands = Object.values(HOST_COMMANDS);
  assert.deepEqual(
    Object.keys(HOST_COMMAND_CAPABILITIES).sort(),
    [...commands].sort(),
    "every allowlisted host command must declare its capability class",
  );
  for (const command of commands) {
    const capability = hostCommandCapability(command);
    assert.ok(capability in browser, `${command} declares unknown capability ${capability}`);
    assert.notEqual(capability, "kind");
    assert.equal(hostSupportsCommand(command, "browser"), false, command);
    assert.equal(hostSupportsCommand(command, "desktop"), true, command);
  }

  const clients = sourceFiles()
    .filter((file) => file !== "app/host/hostCapabilities.ts")
    .filter((file) => file !== "vite-env.d.ts");
  const offenders = clients.filter((file) => {
    const source = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
    return (
      source.includes("__TAURI_INTERNALS__") ||
      source.includes("tauri.localhost") ||
      source.includes("@tauri-apps/api/core") ||
      source.includes('protocol === "tauri:"') ||
      /invoke(<[^>]*>)?\(\s*"/.test(source)
    );
  });
  assert.deepEqual(offenders, [], "native detection/invocation must stay inside hostCapabilities.ts");

  const client = readWebSource("api/client.ts");
  const store = readWebSource("stores/api.ts");
  assert.match(client, /const isDesktopShell = resolveHostKind\(\) === "desktop";/);
  assert.match(client, /tryHostCommand\(HOST_COMMANDS\.notifyClientReady\)/);
  assert.match(client, /tryHostCommand\(HOST_COMMANDS\.clearSessionData\)/);
  assert.match(client, /tryHostCommand<DesktopDeploymentConfig>/);
  assert.match(store, /const isDesktop = isDesktopHost\(\);/);
  assert.match(store, /requireHostCommand<string>\(HOST_COMMANDS\.startLoopbackAuth\)/);
  assert.match(store, /requireHostCommand<string>\(HOST_COMMANDS\.openBrowserLoginAndWait/);
  assert.equal(store.includes("__TAURI_INTERNALS__"), false);
  for (const command of Object.values(HOST_COMMANDS)) {
    assert.equal(client.includes(`invoke("${command}")`), false, command);
  }
});

test("the host bridge fails soft in a browser and throws only when required", async () => {
  assert.equal(await tryHostCommand(HOST_COMMANDS.notifyClientReady, undefined, "browser"), null);
  await assert.rejects(
    () => requireHostCommand(HOST_COMMANDS.startLoopbackAuth, undefined, "browser"),
    /requires the desktop shell/,
  );
  // A non-allowlisted command never reaches the shell, even if the caller is native.
  await assert.rejects(
    () => requireHostCommand("not_a_command" as never, undefined, "desktop"),
    /requires the desktop shell/,
  );
});

test("the shell primitive exposes exactly the shell vocabulary", () => {
  const tabs = readWebSource("components/ui/WorkspaceTabs.tsx");
  const marker = /export type ShellRegionMarker =([\s\S]*?);/.exec(tabs)?.[1] ?? "";
  assert.notEqual(marker, "", "WorkspaceTabs must declare the shell region marker union");
  const declared = [...marker.matchAll(/"([a-z-]+)"/g)].map((match) => match[1]);
  assert.deepEqual(declared.sort(), [...SHELL_REGIONS].sort());
  assert.match(tabs, /data-shell-region=\{shellRegion\}/);
});
