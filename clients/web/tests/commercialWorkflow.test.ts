import assert from "node:assert/strict";
import test from "node:test";
import {
  DECISION_TASKS,
  PORTFOLIO_TASKS,
  classifyRouteFeasibility,
  decisionTaskFromLocation,
  decisionTaskToSearch,
  portfolioTaskFromLocation,
  portfolioTaskToSearch,
} from "../src/app/model/commercialWorkflowModel.ts";

function route(overrides: Record<string, unknown> = {}) {
  return {
    route_id: "route-1",
    route_name: "Route 1",
    start_point_name: "NBP",
    target_point_name: "TTF",
    required_tso_access: [],
    ...overrides,
  } as Parameters<typeof classifyRouteFeasibility>[0];
}

test("portfolio tasks are overview resources routes exposure", () => {
  assert.deepEqual(PORTFOLIO_TASKS, ["overview", "resources", "routes", "exposure"]);
  assert.deepEqual(DECISION_TASKS, ["scenario", "optimize", "review"]);
});

test("portfolio and decision task deep links preserve context", () => {
  assert.equal(portfolioTaskFromLocation("?task=routes"), "routes");
  assert.equal(portfolioTaskFromLocation("?task=unknown"), "overview");
  assert.equal(decisionTaskFromLocation("?task=review"), "review");
  assert.equal(decisionTaskFromLocation("?task=unknown"), "scenario");
  assert.equal(decisionTaskFromLocation("?workspace=review"), "review");
  assert.equal(decisionTaskFromLocation("?workspace=scenario"), "scenario");
  assert.equal(
    portfolioTaskToSearch("?gasDay=2026-09-07", "resources"),
    "gasDay=2026-09-07&workspace=contracts&task=resources",
  );
  assert.equal(
    decisionTaskToSearch("?gasDay=2026-09-07", "optimize"),
    "gasDay=2026-09-07&workspace=scenario&task=optimize",
  );
});

test("route feasibility is conservative and never treats unknown as feasible", () => {
  const candidate = route();
  assert.equal(classifyRouteFeasibility(candidate, null, null), "UNKNOWN");
  const blocked = route({ required_tso_access: ["GTS"] });
  assert.equal(classifyRouteFeasibility(blocked, null, null), "BLOCKED");
});
