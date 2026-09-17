/**
 * Governed research run action tests (Architecture V2 Wave 7 convergence, Wave 9 geography).
 *
 * The research surface could always start a run, but it decided almost nothing: the button was
 * enabled for any non-empty objective, the request named a profile the client had no basis to
 * choose, and what "allow strategy generation" means was left to the run record. These tests
 * pin the rule the surface now gates on - the route's own objective bounds, the runtime
 * database the run needs, the request it actually sends - and the wiring that puts the action
 * in the workspace's primary slot while the panel keeps configuring and reporting it.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  AGENT_RUN_DISCLOSURES,
  AGENT_RUN_OBJECTIVE_MAX_LENGTH,
  AGENT_RUN_OBJECTIVE_MIN_LENGTH,
  agentResearchRequest,
  agentRunReadiness,
  agentStrategyDisclosure,
} from "../src/app/model/agentRunModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function readiness(overrides: Partial<Parameters<typeof agentRunReadiness>[0]> = {}) {
  return agentRunReadiness({
    objective: "Curve shape versus storage economics",
    runtimeDbReady: true,
    running: false,
    ...overrides,
  });
}

test("the objective bounds are the ones the research route enforces", () => {
  // Mirrored from the route's own request model, and asserted at the boundaries so a change
  // on either side fails here rather than in production.
  assert.equal(AGENT_RUN_OBJECTIVE_MIN_LENGTH, 8);
  assert.equal(AGENT_RUN_OBJECTIVE_MAX_LENGTH, 4000);

  assert.deepEqual(readiness({ objective: "1234567" }).blockerKeys, [
    "agents.blocker.objective_short",
  ]);
  assert.deepEqual(readiness({ objective: "12345678" }).blockerKeys, []);
  assert.deepEqual(readiness({ objective: "  short  " }).blockerKeys, [
    "agents.blocker.objective_short",
  ]);

  const atMaximum = "x".repeat(AGENT_RUN_OBJECTIVE_MAX_LENGTH);
  assert.deepEqual(readiness({ objective: atMaximum }).blockerKeys, []);
  assert.deepEqual(readiness({ objective: `${atMaximum}x` }).blockerKeys, [
    "agents.blocker.objective_long",
  ]);
  // Surrounding whitespace is not part of the objective, so it cannot push a valid one over
  // the route's limit.
  assert.deepEqual(readiness({ objective: `  ${atMaximum}  ` }).blockerKeys, []);
});

test("the run is refused without a runtime database, and while one is in flight", () => {
  // The route answers 503 without a configured runtime PostgreSQL, because the run persists
  // its plan, findings and job record. Offering the action anyway would be a lie.
  const noDatabase = readiness({ runtimeDbReady: false });
  assert.equal(noDatabase.canRun, false);
  assert.deepEqual(noDatabase.blockerKeys, ["agents.blocker.runtime_db"]);
  assert.equal(noDatabase.firstBlockerKey, "agents.blocker.runtime_db");

  const inFlight = readiness({ running: true });
  assert.equal(inFlight.canRun, false);
  assert.deepEqual(inFlight.blockerKeys, ["agents.blocker.in_flight"]);

  // A transient state never hides a real precondition, and both are reported.
  const both = readiness({ runtimeDbReady: false, running: true });
  assert.deepEqual(both.blockerKeys, [
    "agents.blocker.runtime_db",
    "agents.blocker.in_flight",
  ]);

  const ready = readiness();
  assert.equal(ready.canRun, true);
  assert.deepEqual(ready.blockerKeys, []);
  assert.equal(ready.firstBlockerKey, null);
});

test("the request carries what the user decided and nothing the surface invented", () => {
  assert.deepEqual(agentResearchRequest({ objective: "  Storage spread  ", allowStrategy: false }), {
    objective: "Storage spread",
    strategy_generation_allowed: false,
  });

  // No client-chosen `agent_profile`: the profile is recorded on the run and scopes its job,
  // but it does not yet change what the orchestrator executes, so choosing one here would
  // imply a capability that does not exist. No `strategy_ir`, no frozen version and no period
  // bounds either - the surface sends none rather than inventing evidence.
  const request = agentResearchRequest({ objective: "Storage spread", allowStrategy: true });
  assert.deepEqual(Object.keys(request).sort(), ["objective", "strategy_generation_allowed"]);
  assert.equal("agent_profile" in request, false);
  assert.equal("strategy_ir" in request, false);
  assert.equal("frozen_strategy_version_id" in request, false);
  assert.equal("period_start_utc" in request, false);
  assert.equal("period_end_utc" in request, false);
});

test("the surface states what strategy generation does before the run, in both states", () => {
  assert.deepEqual(agentStrategyDisclosure(false), ["agents.strategy.off"]);

  // Freezing a StrategyVersion and backtesting it are human acts, so a generation run
  // without a frozen version stops for confirmation rather than backtesting.
  assert.deepEqual(agentStrategyDisclosure(true), [
    "agents.strategy.human_confirmation_required",
    "agents.strategy.no_frozen_version",
  ]);
  assert.equal(AGENT_RUN_DISCLOSURES.length, 2);
  assert.ok(AGENT_RUN_DISCLOSURES.includes("agents.scope.disclosure"));
  assert.ok(AGENT_RUN_DISCLOSURES.includes("agents.profile.recorded"));
});

test("every key the rule can report exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  // The rule returns keys rather than copy, so a key with no translation would surface as a
  // raw identifier. Enumerate them by exercising the rule rather than by listing them here.
  const keys = new Set<string>([
    ...readiness({ runtimeDbReady: false }).blockerKeys,
    ...readiness({ objective: "" }).blockerKeys,
    ...readiness({ objective: "x".repeat(AGENT_RUN_OBJECTIVE_MAX_LENGTH + 1) }).blockerKeys,
    ...readiness({ running: true }).blockerKeys,
    ...agentStrategyDisclosure(true),
    ...agentStrategyDisclosure(false),
    ...AGENT_RUN_DISCLOSURES,
    "agents.readiness.title",
    "agents.readiness.ready",
    "agents.readiness.blocked",
    "agents.run_research",
    "agents.run_research_hint",
  ]);
  assert.ok(keys.size >= 14, `only ${keys.size} keys were enumerated`);

  for (const key of keys) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});

test("the workspace header starts the run and the panel only configures and reports it", () => {
  const workspace = readWebSource("components/AgentsWorkspace.tsx");

  // The rule is applied, not restated.
  assert.match(
    workspace,
    /import \{\s*AGENT_RUN_DISCLOSURES,\s*agentResearchRequest,\s*agentRunReadiness,\s*agentStrategyDisclosure,\s*\} from "@\/app\/model\/agentRunModel";/s,
  );
  assert.match(
    workspace,
    /const readiness = useMemo\(\s*\(\) => agentRunReadiness\(\{ objective, runtimeDbReady, running \}\),\s*\[objective, runtimeDbReady, running\],\s*\);/s,
  );
  assert.match(workspace, /api\.runAgentResearch\(\s*agentResearchRequest\(\{ objective, allowStrategy \}\),\s*\)/s);
  assert.match(workspace, /if \(!readiness\.canRun\) return;/);

  // The action is the header's, disabled by the rule and explained by the first blocker.
  assert.match(workspace, /primaryAction=\{primaryAction\}/);
  assert.match(workspace, /disabled=\{!readiness\.canRun\}/);
  assert.match(workspace, /title=\{\s*readiness\.firstBlockerKey/);
  // ...and it no longer exists inside the panel, which has no run control at all.
  assert.equal(workspace.includes('className="button primary"'), false);

  // The panel reports the verdict: every blocker and what the run will and will not do.
  assert.match(
    workspace,
    /readiness\.blockerKeys\.map\(\(key\) => \(\s*<li key=\{key\}>\{t\(key\)\}<\/li>,?\s*\)\)/s,
  );
  assert.match(workspace, /\[\.\.\.strategyDisclosure, \.\.\.AGENT_RUN_DISCLOSURES\]\.map/);

  // A run is read back from the backend rather than only echoed from the response.
  assert.match(workspace, /const refreshed = await api\.agentRuns\(\);/);
  assert.match(workspace, /setRuns\(refreshed\.data\);/);
});

test("the renderer supplies the runtime-database fact the run is gated on", () => {
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  assert.match(renderer, /<AgentsWorkspace/);
  assert.match(
    renderer,
    /runtimeDbReady=\{\s*api\.runtimeDb\?\.database_url_present === true && api\.runtimeDb\.connectivity\.ok\s*\}/s,
  );
  // The fact comes from the runtime status the shell already read; the surface fetches nothing
  // of its own to decide whether it may run.
  const workspace = readWebSource("components/AgentsWorkspace.tsx");
  assert.equal(workspace.includes("runtimeDb"), true);
  assert.equal(workspace.includes('"/runtime'), false);
});
