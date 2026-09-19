/**
 * The agents workspace's declared reads (slice E of the D3 decision).
 *
 * Three declared calls had no consumer: the profile catalogue a run is filed under, the single-run
 * read that answers for a run outside the bounded list, and the capability search route. Each one
 * answers something the workspace could not:
 *
 * - `GET /api/agent/profiles` publishes the profiles a run may be filed under, which is what makes
 *   the label on a run row checkable and what a `PROFILE_STAGES_NOT_REACHED` warning refers to;
 * - `GET /api/agent/runs/{id}` answers for one run, while the list is bounded, so a run cited by a
 *   Decision Case or a colleague could not be opened at all;
 * - `GET /api/capabilities/search` searches the catalogue's description, domain, tags and input
 *   concepts, which a client-side filter over the rendered rows cannot see.
 *
 * These tests hold the surface to those calls, and hold a failed read to the error taxonomy rather
 * than a raw transport string.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("the bounded run list can be completed by the single-run read", () => {
  const workspace = readWebSource("components/AgentsWorkspace.tsx");

  // The lookup resolves the id through the route that answers for one run, and only when the list
  // does not already hold it - a row the list has is opened like any other row.
  assert.match(workspace, /api\.agentRun\(wanted\)/);
  assert.match(workspace, /runs\.find\(\(item\) => item\.agent_run_id === wanted\)/);
  // The run joins the list it belongs in and is published for the Inspector subject, so a hand-over
  // does not depend on the run having arrived through the list read.
  assert.match(workspace, /setRuns\(\(current\) => \[response\.data, \.\.\.current\]\)/);
  assert.match(workspace, /publishAgentRunsRead\(\[response\.data, \.\.\.runs\]\)/);
  // A refused id is stated, not swallowed.
  assert.match(workspace, /if \(!wanted\) return;/);
});

test("the capability search goes to the route that owns the search", () => {
  const workspace = readWebSource("components/AgentsWorkspace.tsx");

  assert.match(workspace, /api\.searchCapabilities\(query\)/);
  // An empty query restores the whole catalogue instead of searching for nothing.
  assert.match(workspace, /if \(!query\) \{/);
  assert.match(workspace, /const response = await api\.capabilities\(\);/);
  // The search is reachable from the keyboard, not only from the button.
  assert.match(workspace, /event\.key === "Enter"/);
});

test("the profile catalogue is read once and its absence is stated as a declaration", () => {
  const workspace = readWebSource("components/AgentsWorkspace.tsx");

  assert.match(workspace, /api\.agentProfiles\(\)/);
  assert.match(workspace, /void loadAgentProfiles\(\)/);
  assert.match(workspace, /const \[profilesRead, setProfilesRead\] = useState\(false\)/);
  assert.match(workspace, /setProfilesRead\(true\)/);

  // An unread catalogue is not a catalogue that declares nothing. The panel says which one it is.
  assert.match(
    workspace,
    /profilesRead \? t\("agents\.profiles_none"\) : t\("data\.unavailable"\)/,
  );
  // A profile that declares no stage declares that, rather than reading as a failed read.
  assert.match(workspace, /declared\.join\(", "\) \|\| t\("agents\.profile_stages_none"\)/);
  assert.equal(/declared\.join\(", "\) \|\| t\("data\.unavailable"\)/.test(workspace), false);
});

test("a failed read is presented through the taxonomy, never as a raw transport string", () => {
  const workspace = readWebSource("components/AgentsWorkspace.tsx");

  // The envelope is kept as it arrived, so the presentation can read its code, family and
  // correlation id; flattening it to text at the catch site is what made a catalogued refusal read
  // as an unclassified fault.
  assert.equal(workspace.includes("setError(String("), false);
  assert.match(workspace, /const \[error, setError\] = useState<unknown>\(null\)/);
  assert.match(workspace, /presentError\(t, describeFailure\(error\)\)/);
  assert.match(workspace, /\{failure\.title\}/);
  assert.match(workspace, /\{failure\.action\}/);
  assert.match(workspace, /failure\.correlationId/);
});

test("the agent catalogue vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "agents.profiles",
    "agents.profiles_note",
    "agents.profiles_none",
    "agents.profile",
    "agents.profile_stages",
    "agents.profile_stages_none",
    "agents.profile_purpose",
    "agents.search_capabilities",
    "agents.search_capabilities_placeholder",
    "agents.search",
    "agents.open_run_by_id",
    "agents.open_run",
    "errors.correlation_id",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }

  // The run-id field's placeholder is an identifier shape rather than prose, so it is the same text
  // in both locales - and `localeDistinctness.test.ts` is where that deliberate sameness is pinned.
  assert.equal(en["agents.run_id_placeholder"], zh["agents.run_id_placeholder"]);
});
