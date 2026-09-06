import assert from "node:assert/strict";
import test from "node:test";
import {
  STRATEGY_TASKS,
  MAX_COMPARE_RUNS,
  classifyRunCompatibility,
  strategyTaskFromLocation,
  strategyTaskToSearch,
} from "../src/app/model/strategyLabModel.ts";

function run(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "run-1",
    strategy_id: "strategy-1",
    run_type: "BACKTEST",
    backtest_engine_version: "backtest-engine/1",
    evaluation_start_utc: "2026-01-01T00:00:00Z",
    evaluation_end_utc: "2026-02-01T00:00:00Z",
    backtest_metrics: { temporal_integrity: "APPROXIMATE" },
    ...overrides,
  } as Parameters<typeof classifyRunCompatibility>[0][number];
}

test("strategy lab task ids are the four research workflow tasks", () => {
  assert.deepEqual(STRATEGY_TASKS, ["design", "backtest", "compare", "shadow"]);
});

test("strategy lab task deep links and safe fallback", () => {
  assert.equal(strategyTaskFromLocation("?workspace=strategy&task=backtest"), "backtest");
  assert.equal(strategyTaskFromLocation("?workspace=strategy"), "design");
  assert.equal(strategyTaskFromLocation("?workspace=strategy&task=orders"), "design");
  assert.equal(
    strategyTaskToSearch("?gasDay=2026-09-07", "compare"),
    "gasDay=2026-09-07&workspace=strategy&task=compare",
  );
});

test("comparison classifies different strategy as not meaningful", () => {
  const a = run({ run_id: "a", strategy_id: "strategy-a" });
  const b = run({ run_id: "b", strategy_id: "strategy-b" });
  assert.equal(classifyRunCompatibility([a, b]), "NOT_MEANINGFULLY_COMPARABLE");
});

test("comparison flags period or engine or quality differences as caveats", () => {
  const a = run({ run_id: "a" });
  const b = run({ run_id: "b", evaluation_end_utc: "2026-03-01T00:00:00Z" });
  const c = run({ run_id: "c", backtest_engine_version: "backtest-engine/2" });
  const d = run({
    run_id: "d",
    backtest_metrics: { temporal_integrity: "VERIFIED" },
  });
  assert.equal(classifyRunCompatibility([a, b]), "COMPARABLE_WITH_CAVEATS");
  assert.equal(classifyRunCompatibility([a, c]), "COMPARABLE_WITH_CAVEATS");
  assert.equal(classifyRunCompatibility([a, d]), "COMPARABLE_WITH_CAVEATS");
  assert.equal(classifyRunCompatibility([a, run({ run_id: "e" })]), "COMPARABLE");
});

test("compare run cap is explicit", () => {
  assert.equal(MAX_COMPARE_RUNS, 5);
});
