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
  assert.match(
    scoped,
    /for \(const detail of compared\?\.failures \?\? \[\]\) \{\s*recordFailure\(failures, scope, detail\);/,
  );
  // What the comparison could not measure is reported as an observation, from the comparison's
  // own result - never from a guess about the page's copy.
  assert.match(
    scoped,
    /for \(const detail of compared\?\.observations \?\? \[\]\) \{\s*recordObservation\(observations, `\$\{scope\}: \$\{detail\}`\);/,
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
  for (const key of ["market", "agents", "access", "capacity", "research"]) {
    assert.ok(declaredKeys("KNOWN_FUNCTIONAL_GAPS").includes(key), `functional gap kept: ${key}`);
  }
  assert.deepEqual(declaredKeys("KNOWN_SURFACE_DEFECTS").sort(), ["agents"]);

  // The glossary exemption (measured 2026-09-19) is retired, not moved: it was a statement about
  // page copy, and the surface's term index and wiki article are now compared with the surface's
  // own read by exact term id, with its selection exercised as an interaction
  // (`glossaryTermSelectionInteraction`). A surface that renders no term fails by name.
  assert.equal(declaredKeys("KNOWN_FUNCTIONAL_GAPS").includes("glossary"), false);
  assert.equal(declaredKeys("KNOWN_SURFACE_DEFECTS").includes("glossary"), false);

  // The source center's exemption is retired the same way and for the same reason: "sources
  // return rows while the administration surface reports Total sources 0" was a statement about
  // the page's copy, and the surface's catalog is now compared with the registry read by exact
  // source id, with its selection and category filter exercised as an interaction
  // (`sourceCenterSelectionInteraction`). A row the read returned that the catalog does not render
  // - and a row the catalog renders that the read did not return - fails by name.
  assert.equal(declaredKeys("KNOWN_FUNCTIONAL_GAPS").includes("sources"), false);
  assert.equal(declaredKeys("KNOWN_SURFACE_DEFECTS").includes("sources"), false);

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

test("the glossary term index is compared by term id, and its selection is exercised", () => {
  // The retirement of this surface's exemption has to be carried by measurements, not by its
  // absence: the term index is compared with the surface's own read (`/api/glossary`) by exact
  // `term_id`, in both languages and at every viewport, and the two-pane interaction the user
  // asked for is asserted as an interaction - the article must follow the clicked record.
  const signals = block("const SURFACE_SIGNALS = {", "\n};");
  assert.match(
    signals,
    /glossary: \{ heading: \/glossary\/i, apiPath: "\/api\/glossary\?limit=5", readToRender: \[\{ label: "glossary term index", rowsPath: "data", recordIdField: "term_id", rowSelectors: \['\[data-record="glossary-term"\]'\], emptySelector: '\[data-empty-state="glossary-terms"\]' \}\] \},/,
  );

  const interaction = block(
    "async function glossaryTermSelectionInteraction(",
    "\nexport async function runWorkflowSmoke()",
  );
  // A different term is selected: the click only counts because the choice is taken against the
  // read's own ids, by exact equality rather than by a rendered label or a page-wide substring.
  assert.match(interaction, /const next = terms\.find\(\(row\) => row\.id !== initialId\);/);
  assert.match(interaction, /const cardIndex = renderedIds\.indexOf\(next\.id\);/);
  assert.match(interaction, /await page\.locator\('\[data-record="glossary-term"\]'\)\.nth\(cardIndex\)\.click\(\);/);
  // The article must carry the clicked term's own record, and render that term's definition.
  assert.match(interaction, /getAttribute\("data-record-id"\) === id,/);
  assert.match(interaction, /article\.locator\("\.glossary-definition"\)/);
  assert.match(interaction, /if \(expected !== "" && definition !== expected\)/);
  // The index's filter is exercised on the selected term's own name: the one query whose expected
  // answer the read knows without the harness reimplementing the filter's matching rule.
  assert.match(interaction, /page\.locator\("\.glossary-left-rail input"\)\.first\(\)\.fill\(next\.term\)/);
  assert.match(interaction, /filtering the term index by '\$\{next\.term\}' hides the term its own read returned/);
  // A selection that does not reach the article, an article that opens on no returned term, and an
  // index that never rendered the term are failures, never observations.
  assert.match(interaction, /left the wiki article on/);
  assert.match(interaction, /which the glossary read did not return/);
  assert.match(interaction, /the term index renders no row for/);
  assert.equal(interaction.includes("recordObservation("), false);
  assert.match(source, /currentScope = "interaction\/glossary-term-selection";/);
  assert.match(source, /await glossaryTermSelectionInteraction\(page, failures\);/);

  // The markers the group and the interaction select are the glossary surface's own.
  const component = readFileSync(new URL("../src/components/GlossaryWiki.tsx", import.meta.url), "utf8");
  assert.match(component, /data-record="glossary-term"/);
  assert.match(component, /data-record-id=\{term\.term_id\}/);
  assert.match(component, /data-empty-state="glossary-terms"/);
  assert.match(component, /data-record="glossary-article"/);
  assert.match(component, /data-record-id=\{selectedTerm\?\.term_id\}/);
});

test("the source catalog is compared by source id, in the task that renders the whole read", () => {
  // The surface's declaration was page copy ("sources return rows while the administration surface
  // reports Total sources 0"), produced by a whole-page match over the first 400 characters that
  // could not see the table, name a row, or read the Chinese page. The registry read
  // (`GET /api/sources`, the route the client lane reads) is now compared with the catalog table
  // row by row, by each source's own `source_id`, and the surface's selection and category filter
  // are exercised as interactions.
  const signals = block("const SURFACE_SIGNALS = {", "\n};");
  const sources = block("sources: { heading: /source/i", "glossary: {");
  assert.match(sources, /apiPath: "\/api\/sources"/);
  assert.match(sources, /recordIdField: "source_id"/);
  assert.match(sources, /rowSelectors: \['\[data-record="source-row"\]'\]/);
  assert.match(sources, /emptySelector: '\[data-empty-state="source-rows"\]'/);
  // The surface opens on its priority queue, a filtered subset of the same read, so the group names
  // the catalog task: the comparison is never filtered rows against an unfiltered read.
  assert.match(sources, /taskTab: "source-tab-catalog"/);
  // The registry read is the catalog's whole row set, not a bound over one: a rendered row the read
  // did not return is a failure too, not only a row the read returned and the surface did not.
  assert.match(sources, /exactRows: true/);
  assert.doesNotMatch(sources, /rowLimit/);
  assert.doesNotMatch(signals, /apiPath: "\/api\/sources\?limit=5"/);

  // The declared task is activated before the evidence is collected and the task that was active is
  // restored afterwards, so the screenshot keeps showing the task the deep link opened. A task that
  // never becomes active, and a restore that fails, are failures rather than silent comparisons in
  // another task's rows.
  const scoped = block("if (signal.readToRender) {", "} else if (state.apiRows !== null && state.apiRows > 0) {");
  assert.match(scoped, /const restoreTab = await selectedTaskTabId\(page, tabId\);/);
  assert.match(scoped, /if \(await activateTaskTab\(page, tabId\)\) \{/);
  assert.match(scoped, /the '\$\{tabId\}' task never became the active one/);
  assert.match(scoped, /the sweep could not restore the '\$\{tabId\}' task/);
  assert.ok(
    scoped.indexOf("await activateTaskTab(page, tabId)") < scoped.indexOf("collectVisibleElements"),
    "the task is activated before the rows are collected",
  );
  const helpers = block("async function selectedTaskTabId(", "async function inspectSurfaceFunction(");
  assert.match(helpers, /aria-selected="true"/);
  assert.match(helpers, /timeout: 5_000/);
  assert.equal(helpers.includes("recordObservation("), false);

  const interaction = block(
    "async function sourceCenterSelectionInteraction(",
    "\nfunction catalogRendersExactly(",
  );
  // The catalog is compared in the surface's own task, by the read's ids in both directions: a row
  // the read returned but the catalog does not render, and a row the catalog renders that the read
  // did not return, are both failures - never a pass.
  assert.match(interaction, /if \(!\(await activateTaskTab\(page, "source-tab-catalog"\)\)\) \{/);
  assert.match(interaction, /not in the read/);
  assert.match(interaction, /the catalog does not render the sources its own read returned/);
  assert.match(interaction, /the detail panel opens on/);
  assert.match(interaction, /which the sources read did not/);
  // The selection is taken by exact id, not by a rendered label or an index into the page.
  assert.match(
    interaction,
    /page\.locator\(`\[data-record="source-row"\]\[data-record-id="\$\{next\.id\}"\]`\)/,
  );
  assert.match(interaction, /await row\.first\(\)\.locator\("\.source-row-select"\)\.click\(\);/);
  assert.match(interaction, /left the detail panel on/);
  assert.match(interaction, /detail\.locator\("h2"\)/);
  // The filter is exercised on a category the read itself declares for that row, and the expected
  // answer is the read's own rows of that category: the harness never reimplements the filter's
  // matching rule, and asking for "all" again must bring the whole read back.
  assert.match(
    interaction,
    /page\.locator\(`\[data-source-category="\$\{next\.category\}"\]`\)/,
  );
  assert.match(interaction, /the surface offers no category filter for/);
  assert.match(interaction, /its own read declares for '\$\{next\.id\}'/);
  assert.match(interaction, /did not leave exactly the rows its own read/);
  assert.match(interaction, /is not the one the surface reports as pressed/);
  assert.match(interaction, /asking for the 'all' category did not put the catalog back on every row/);
  assert.equal(interaction.includes("recordObservation("), false);
  // The interaction clicks the surface's own controls only: no ingestion run, no credential write.
  assert.equal(interaction.includes("requestSourceRun"), false);
  assert.equal(interaction.includes("saveProviderCredential"), false);
  assert.equal(interaction.includes("POST"), false);
  assert.match(source, /currentScope = "interaction\/source-center-selection";/);
  assert.match(source, /await sourceCenterSelectionInteraction\(page, failures\);/);

  // The bounded wait's predicate is serialised into the page, so it must be self-contained.
  const predicate = block("function catalogRendersExactly(", "\nexport async function runWorkflowSmoke()");
  assert.match(predicate, /document\.querySelectorAll\('\[data-record="source-row"\]'\)/);
  assert.equal(predicate.includes("renderedRowIds"), false);

  // The markers the group and the interaction select are the source surface's own.
  const component = readFileSync(new URL("../src/components/SourceCenter.tsx", import.meta.url), "utf8");
  assert.match(component, /data-record="source-row"/);
  assert.match(component, /data-record-id=\{source\.source_id\}/);
  assert.match(component, /data-empty-state="source-rows"/);
  assert.match(component, /data-record="source-detail"/);
  assert.match(component, /data-record-id=\{selectedSource\?\.source_id\}/);
  assert.match(component, /data-source-category=\{category\}/);
});
