/**
 * Strategy backtest run rule tests (Architecture V2 Wave 9, action geography).
 *
 * Running a backtest is a `compute` consequence, so the geography puts it in the workspace's
 * single primary slot. That was impossible while the rule lived in the configuring panel -
 * the blockers, the period and the assumptions were panel state - so the rule moved into
 * `app/model/strategyBacktestModel.ts` and the workspace owns the draft. These tests pin the
 * rule at its own thresholds and the wiring that keeps the panel reporting while the header
 * acts.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  MISSING_DATA_POLICIES,
  TRANSACTION_COST_TREATMENTS,
  strategyBacktestReadiness,
  strategyBacktestRequest,
  type StrategyBacktestDraft,
} from "../src/app/model/strategyBacktestModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function draft(overrides: Partial<StrategyBacktestDraft> = {}): StrategyBacktestDraft {
  return {
    start: "2026-01-01",
    end: "2026-02-01",
    missingDataPolicy: "FAIL",
    transactionCostTreatment: "UNAVAILABLE",
    transactionCost: "",
    ...overrides,
  };
}

function readiness(overrides: Partial<Parameters<typeof strategyBacktestReadiness>[0]> = {}) {
  return strategyBacktestReadiness({
    draft: draft(),
    frozen: true,
    running: false,
    ...overrides,
  });
}

test("a frozen version over a real period with no modeled cost may run", () => {
  assert.deepEqual(readiness(), { canRun: true, blockerKeys: [], firstBlockerKey: null });
});

test("an unfrozen version is refused, because the platform would refuse it too", () => {
  // A backtest evaluates a frozen version: its numbers cannot move under the run. A surface
  // that offered the run anyway would be offering a refusal.
  const state = readiness({ frozen: false });
  assert.equal(state.canRun, false);
  assert.deepEqual(state.blockerKeys, ["strategy_lab.blocker.frozen_required"]);
  assert.equal(state.firstBlockerKey, "strategy_lab.blocker.frozen_required");
});

test("the period must be a real interval", () => {
  for (const period of [
    { start: "", end: "2026-02-01" },
    { start: "2026-01-01", end: "" },
    { start: "2026-02-01", end: "2026-02-01" },
    { start: "2026-03-01", end: "2026-02-01" },
  ]) {
    const state = readiness({ draft: draft(period) });
    assert.equal(state.canRun, false, JSON.stringify(period));
    assert.ok(state.blockerKeys.includes("strategy_lab.blocker.period"));
  }
  // An adjacent period is a real interval.
  assert.equal(readiness({ draft: draft({ start: "2026-01-01", end: "2026-01-02" }) }).canRun, true);
});

test("a modeled transaction cost must be a number, and is only read when modeled", () => {
  // A modeled cost that is silently zero would change the *result* rather than the request,
  // so an unparseable one blocks the run.
  const broken = readiness({
    draft: draft({ transactionCostTreatment: "MODELED_COST", transactionCost: "abc" }),
  });
  assert.equal(broken.canRun, false);
  assert.deepEqual(broken.blockerKeys, ["strategy_lab.blocker.transaction_cost"]);

  // The same text is harmless while the treatment says the cost is not modeled: the field is
  // not read, so it cannot make the request wrong.
  assert.equal(
    readiness({
      draft: draft({ transactionCostTreatment: "UNAVAILABLE", transactionCost: "abc" }),
    }).canRun,
    true,
  );
  assert.equal(
    readiness({
      draft: draft({ transactionCostTreatment: "MODELED_COST", transactionCost: "0.25" }),
    }).canRun,
    true,
  );
});

test("a run in flight blocks the next one and never hides a real precondition", () => {
  assert.deepEqual(readiness({ running: true }).blockerKeys, ["strategy_lab.blocker.in_flight"]);
  assert.deepEqual(readiness({ frozen: false, running: true }).blockerKeys, [
    "strategy_lab.blocker.frozen_required",
    "strategy_lab.blocker.in_flight",
  ]);
});

test("the request carries the configured assumptions and nothing invented", () => {
  const request = strategyBacktestRequest(
    draft({
      transactionCostTreatment: "MODELED_COST",
      transactionCost: "0.4",
      missingDataPolicy: "SKIP_DECISION",
    }),
    "version-7",
  );

  assert.deepEqual(request, {
    strategy_version_id: "version-7",
    evaluation_period_start_utc: "2026-01-01T00:00:00Z",
    evaluation_period_end_utc: "2026-02-01T00:00:00Z",
    economic_assumptions: {
      missing_data_policy: "SKIP_DECISION",
      // The fill-price policy is a declared backend assumption, not a user choice on this
      // surface, and it is sent as the constant it is.
      fill_price_policy: "NEXT_ELIGIBLE",
      cost_components: [
        { code: "TRANSACTION_COST", treatment: "MODELED_COST", amount_gbp_mwh: 0.4 },
      ],
    },
  });

  // No version is no request: the surface refuses rather than posting one without a version.
  assert.equal(strategyBacktestRequest(draft(), null), null);
  assert.equal(strategyBacktestRequest(draft(), ""), null);

  // The selectable vocabularies are the ones the backend accepts, declared once.
  assert.deepEqual([...MISSING_DATA_POLICIES], ["FAIL", "SKIP_DECISION", "CARRY_FORWARD_WITH_MAX_AGE"]);
  assert.deepEqual([...TRANSACTION_COST_TREATMENTS], ["UNAVAILABLE", "MODELED_COST", "EXCLUDED"]);
});

test("the workspace hosts the action and the panel only configures and reports", () => {
  const workspace = readWebSource("components/strategy/StrategyLabWorkspace.tsx");
  const panel = readWebSource("components/strategy/StrategyBacktestWorkspace.tsx");

  // The draft and the rule are the workspace's, and the header action is derived from them.
  assert.match(workspace, /const \[backtestDraft, setBacktestDraft\] = useState<StrategyBacktestDraft>/);
  assert.match(
    workspace,
    /const backtestReadiness = strategyBacktestReadiness\(\{\s*draft: backtestDraft,\s*frozen: controller\.selectedVersion\?\.status === "FROZEN",\s*running: controller\.loading,\s*\}\);/s,
  );
  assert.match(workspace, /primaryAction=\{primaryAction\}/);
  assert.match(workspace, /onDraftChange=\{setBacktestDraft\}/);

  // The panel no longer decides or starts anything: no run call, no rule evaluation of its
  // own, and it renders the blockers from the keys it was handed.
  assert.equal(panel.includes("controller.runBacktest"), false);
  assert.equal(panel.includes("strategyBacktestReadiness"), false);
  assert.equal(panel.includes("useState(\"FAIL\")"), false);
  assert.match(panel, /readiness\.blockerKeys\.map\(\(key\) => <span key=\{key\} className="status-badge status-blocked">\{t\(key\)\}<\/span>\)/);
  assert.match(panel, /const updateDraft = \(patch: Partial<StrategyBacktestDraft>\) =>/);
  // The local view switch stays local: it is a read consequence, not the run.
  assert.match(panel, /const \[mode, setMode\] = useState<"configure" \| "result">\("configure"\)/);
});

test("every new strategy string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  for (const key of [
    "strategy_lab.run_backtest",
    "strategy_lab.run_backtest_hint",
    "strategy_lab.blocker.frozen_required",
    "strategy_lab.blocker.period",
    "strategy_lab.blocker.transaction_cost",
    "strategy_lab.blocker.in_flight",
  ]) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
