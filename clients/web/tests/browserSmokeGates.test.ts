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
  const reactCheck = block("if (state.reactErrors", "if (state.apiRows !== null");
  assert.match(reactCheck, /recordFailure\(\s*failures,\s*scope,/);
  // The captured stack stays in the failure, because the message alone names no renderer.
  assert.match(reactCheck, /state\.reactErrors\[0\]\.stack/);
  assert.equal(reactCheck.includes("recordObservation("), false);

  // The stack capture is still installed before the app loads.
  assert.match(source, /await installReactErrorStackCapture\(page\);/);
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
