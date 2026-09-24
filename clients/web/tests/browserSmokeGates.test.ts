/**
 * The browser acceptance gate must fail on the defects it has already measured.
 *
 * The map page's blank view was carried as a declared exemption and React's internal error as an
 * observation, so a green sweep did not prove those paths were usable. Both are repaired and their
 * exemptions are gone; the unrelated declared defects stay declared. This reads the harness source
 * because the harness itself needs a browser, a migrated database and a seeded identity to run.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const HARNESS = new URL("../../../scripts/uat/browser_workflow_smoke.mjs", import.meta.url);
const source = readFileSync(HARNESS, "utf8");

function block(startMarker: string, endMarker: string): string {
  const start = source.indexOf(startMarker);
  assert.notEqual(start, -1, `missing marker: ${startMarker}`);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(end, -1, `missing marker after ${startMarker}: ${endMarker}`);
  return source.slice(start, end);
}

/** Top-level keys of one declared map, in source order. */
function declaredKeys(constantName: string): string[] {
  const body = block(`const ${constantName} = {`, "\n};");
  return [...body.matchAll(/^\s{2}([a-z_]+):/gm)].map((match) => match[1]);
}

test("no workspace is exempt from rendering its own page", () => {
  // The repaired map page was the one declared here; the declaration is gone with the repair.
  assert.equal(source.includes("KNOWN_NON_RENDERING_WORKSPACES"), false);

  const blankPageCheck = block("if (!state.pageVisible) {", "if (!state.lang");
  assert.match(blankPageCheck, /recordFailure\(\s*failures,\s*scope,/);
  assert.match(blankPageCheck, /no workspace page is displayed/);
  assert.equal(blankPageCheck.includes("recordObservation("), false);
});

test("a React internal error fails the run instead of joining the observations", () => {
  // The block ends at the next branch, which is now the scoped read-to-render check: the
  // contracts/orders surfaces stopped using the whole-page heuristic, so the weaker check below
  // is no longer the first thing after the React-error check.
  const reactCheck = block("if (state.reactErrors", "if (signal.readToRender) {");
  assert.match(reactCheck, /recordFailure\(\s*failures,\s*scope,/);
  // The captured stack stays in the failure, because the message alone names no renderer.
  assert.match(reactCheck, /state\.reactErrors\[0\]\.stack/);
  assert.equal(reactCheck.includes("recordObservation("), false);

  // The stack capture is still installed before the app loads.
  assert.match(source, /await installReactErrorStackCapture\(page\);/);
});

test("the repaired surfaces compare rendered rows with their own read, not with page copy", () => {
  // CI run 35996627042 failed contracts and orders as "the read returned 1 row(s) and the surface
  // renders none of them". The verdict came from a page-wide `n/a`/`unavailable` match and a row
  // count that treated an aggregate body as one row. Both surfaces now declare what their reads
  // return and which rendered rows are compared, by exact record id and within each group's own
  // selector, so one group's rows (or the page's copy) cannot stand in for another's.
  const signals = block("const SURFACE_SIGNALS = {", "\n};");
  assert.match(
    signals,
    /contracts: \{ heading: \/portfolio\|contract\/i, apiPath: "\/api\/route-cost\/upstream-contracts", readToRender: \[/,
  );
  assert.match(
    signals,
    /orders: \{ heading: \/portfolio\|order\/i, apiPath: "\/api\/projections\/portfolio-snapshot", readToRender: \[/,
  );
  for (const group of ["rowsPath", "recordIdField", "rowSelectors"]) {
    assert.ok(signals.includes(group), `the scoped groups declare ${group}`);
  }
  // A signal-level row selector would be dead configuration: the rows a group compares are the
  // ones its own selector collects.
  assert.doesNotMatch(signals, /rowSelector: /);
  // Display-text matching is gone: identity is the record's own id, carried by the row element.
  assert.doesNotMatch(signals, /identityFields|identityMode/);
  assert.match(signals, /recordIdField: "contract_id"/);
  assert.match(signals, /recordIdField: "order_observation_id"/);
  assert.match(signals, /recordIdField: "pnl_snapshot_id"/);
  // The orders empty states are declared markers of their own, not "any row in the table".
  assert.match(signals, /emptySelector: '\[data-empty-state="screen-orders"\]'/);
  assert.match(signals, /emptySelector: '\[data-empty-state="pnl-snapshots"\]'/);
  assert.doesNotMatch(signals, /orders: \{[^}]*live-summary/);

  // The scoped branch reads the surface's own endpoint in the session it holds, collects the
  // rows the surface actually rendered for each group's own selector (visibility-filtered, so a
  // hidden row is not evidence) and compares the two through the module: a failure names the
  // returned rows whose own id no rendered row carries.
  const scoped = block("if (signal.readToRender) {", "} else if (state.apiRows !== null && state.apiRows > 0) {");
  assert.match(scoped, /const groups = signal\.readToRender\.map\(\(group\) => readGroupRows\(state\.apiBody, group\)\)/);
  assert.match(scoped, /await page\.evaluate\(collectVisibleElements, \{\s*groups:/);
  assert.match(scoped, /evaluateReadToRender\(\{\s*status: state\.apiStatus,\s*groups,\s*evidence,/);
  assert.match(scoped, /for \(const detail of compared\.failures\) \{\s*recordFailure\(failures, scope, detail\);/);
  // What the comparison could not measure is reported as an observation, from the comparison's
  // own result - never from a guess about the page's copy.
  assert.match(
    scoped,
    /for \(const detail of compared\.observations\) \{\s*recordObservation\(observations, `\$\{scope\}: \$\{detail\}`\);/,
  );

  // The weaker whole-page heuristic survives only for the surfaces that have not declared a
  // scoped contract, and it is no longer reachable from the repaired ones.
  const legacy = source.slice(source.indexOf("} else if (state.apiRows !== null && state.apiRows > 0) {"));
  assert.ok(legacy.includes("const rendersNothing"), "the weaker check is still the declared one");
  assert.ok(legacy.includes("|unavailable|no records|no data|"), "its page-wide heuristic is intact");
  const scopedIndex = source.indexOf("if (signal.readToRender) {");
  const heuristicIndex = source.indexOf("const rendersNothing");
  assert.ok(scopedIndex !== -1 && heuristicIndex > scopedIndex);
});

test("the unrelated declared defects are still declared, for declared workspaces only", () => {
  const workspaces = [...block("const WORKSPACES = [", "];").matchAll(/"([a-z]+)"/g)].map(
    (match) => match[1],
  );
  assert.ok(workspaces.length >= 16, "the sweep still declares its workspaces");

  for (const constant of ["KNOWN_FUNCTIONAL_GAPS", "KNOWN_SURFACE_DEFECTS"]) {
    const keys = declaredKeys(constant);
    assert.ok(keys.length > 0, `${constant} still declares the gaps the run carries`);
    for (const key of keys) {
      assert.ok(workspaces.includes(key), `${constant} names a declared workspace: ${key}`);
      assert.notEqual(key, "network", `${constant} must not exempt the repaired map page`);
    }
  }

  // The measured-and-open gaps this repair does not touch, recorded in
  // docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md.
  for (const key of ["market", "glossary", "agents", "access", "capacity", "sources", "research"]) {
    assert.ok(declaredKeys("KNOWN_FUNCTIONAL_GAPS").includes(key), `functional gap kept: ${key}`);
  }
  assert.deepEqual(declaredKeys("KNOWN_SURFACE_DEFECTS").sort(), ["agents", "glossary"]);

  // The session bootstrap's expected 401 is still the only allowed console error.
  assert.match(block("const ALLOWED_CONSOLE_ERRORS = [", "];"), /status of 401/);
});

test("the summary separates failures from observations", () => {
  // A declared gap or an unmeasurable check is reported, and the run is green only with no failure.
  assert.match(source, /ok: failures\.length === 0/);
  assert.match(source, /observations,/);
  assert.match(source, /functionalGapCount: functionalGaps\.length/);
});

test("each surface probe reads a route the product serves, not a path no endpoint declares", () => {
  // `contracts` asked for `/api/contracts/upstream?limit=5`, which no route declares: the 404 it
  // returned was the probe's own console error on six scopes, and the surface it was meant to
  // measure was never compared with its data. It now reads the upstream resource terms the shell
  // itself reads (`upstreamContracts` in the client). `tests/contract/test_browser_probe_paths.py`
  // holds the same paths against the application's declared GET surface.
  const signals = block("const SURFACE_SIGNALS = {", "\n};");
  assert.match(
    signals,
    /contracts: \{ heading: \/portfolio\|contract\/i, apiPath: "\/api\/route-cost\/upstream-contracts",/,
  );
  assert.doesNotMatch(signals, /apiPath: "\/api\/contracts\/upstream/);

  const client = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
  assert.match(client, /"\/route-cost\/upstream-contracts"/);
});

test("the functional gate waits for the surface's own read to settle, and fails a stuck one", () => {
  // The gate judges a surface "after load", but it used to evaluate immediately: on CI run
  // 35966584093 it judged surfaces whose workspace batch was still in flight, so pending states
  // were reported as lingering loading copy and as rows the surface never rendered. Waiting for
  // the page's own published load state is the missing "after load"; it is not an exemption,
  // because a page that never settles is recorded as a failure.
  const settle = block("const settled = await page", "const state = await page.evaluate(() => ({");
  assert.match(settle, /dataset\.workspaceLoadState === "settled"/);
  assert.match(settle, /timeout: 20_000/);
  assert.match(settle, /recordFailure\(\s*failures,\s*settleScope,/);
  assert.match(settle, /the workspace read never settled/);
  assert.equal(settle.includes("recordObservation("), false);
  // A false-before-the-read-started boolean would let the sweep race the batch again.
  assert.equal(settle.includes("workspaceLoading"), false);
  // The text-based loading check stays, for the surfaces that are still loading after settling.
  assert.match(source, /"the surface still shows 'Loading workspace' after load"/);
});
