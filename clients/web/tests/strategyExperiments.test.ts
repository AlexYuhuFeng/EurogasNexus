/**
 * Backtest experiments (Wave 9 surface completion).
 *
 * `POST /api/strategy-runs` has accepted an `experiment_id` since the strategy registry shipped, and
 * `POST /api/backtest-experiments` plus its two reads were declared in the client and never called:
 * a run could only be grouped into an experiment by a caller using the API. These tests hold the
 * rule the surface now gates on to the route it mirrors, and hold the panel to the declarations it
 * claims to use.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  endOfDayUtc,
  EXPERIMENT_MAX_PERIOD_DAYS,
  EXPERIMENT_NAME_MAX_LENGTH,
  experimentPeriod,
  experimentReadiness,
  experimentRequest,
  experimentsForStrategy,
  runsInExperiment,
  startOfDayUtc,
  unloadedRunIds,
} from "../src/app/model/strategyExperimentModel.ts";
import type { BacktestExperimentDTO } from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const FROZEN = { strategy_version_id: "sv-1", status: "FROZEN" };
const DRAFT = { strategy_version_id: "sv-2", status: "DRAFT" };
const DRAFT_OK = { name: "NBP sensitivity", hypothesis: "", period: { start: "2025-01-01", end: "2025-12-31" } };

function experiment(overrides: Partial<BacktestExperimentDTO> = {}): BacktestExperimentDTO {
  return {
    experiment_id: "experiment-1",
    strategy_id: "strategy-1",
    base_strategy_version_id: "sv-1",
    name: "NBP sensitivity",
    hypothesis: "",
    experiment_type: "SINGLE_RUN",
    evaluation_period: { start_utc: "2025-01-01T00:00:00Z", end_utc: "2025-12-31T23:59:59Z" },
    run_ids: [],
    status: "OPEN",
    created_by: "analyst-1",
    created_at_utc: "2026-01-01T00:00:00Z",
    updated_at_utc: "2026-01-01T00:00:00Z",
    research_only: true,
    ...overrides,
  };
}

test("the create rule mirrors the route's own refusals", () => {
  // 404 without the strategy the route resolves from the navigator's selection.
  assert.deepEqual(
    experimentReadiness({ subject: { strategyId: null, version: null }, draft: DRAFT_OK }).blockerKeys,
    ["strategy_lab.experiment.blocker.no_strategy"],
  );
  // A strategy without a version cannot name a base version.
  assert.deepEqual(
    experimentReadiness({ subject: { strategyId: "strategy-1", version: null }, draft: DRAFT_OK })
      .blockerKeys,
    ["strategy_lab.experiment.blocker.no_version"],
  );
  // 409: an experiment's base version is immutable, so a draft is refused by the route.
  assert.deepEqual(
    experimentReadiness({ subject: { strategyId: "strategy-1", version: DRAFT }, draft: DRAFT_OK })
      .blockerKeys,
    ["strategy_lab.experiment.blocker.version_not_frozen"],
  );
  assert.equal(
    experimentReadiness({ subject: { strategyId: "strategy-1", version: FROZEN }, draft: DRAFT_OK })
      .canCreate,
    true,
  );
});

test("the period rule mirrors the engine's own bounds", () => {
  const subject = { strategyId: "strategy-1", version: FROZEN };
  const period = (start: string, end: string) =>
    experimentReadiness({ subject, draft: { ...DRAFT_OK, period: { start, end } } }).blockerKeys;

  // 422: the engine refuses a non-ordered period...
  assert.deepEqual(period("2025-12-31", "2025-01-01"), [
    "strategy_lab.experiment.blocker.period_order",
  ]);
  // ...and reports "no period" once rather than twice.
  assert.deepEqual(period("", ""), ["strategy_lab.experiment.blocker.period_required"]);
  // A single day is a real period: the surface anchors the start to 00:00Z and the end to 23:59:59Z,
  // so `2025-01-01 → 2025-01-01` is ordered and accepted rather than refused as "empty".
  assert.deepEqual(period("2025-01-01", "2025-01-01"), []);
  // Times that the caller supplied are respected, so an identical instant is a real violation.
  assert.deepEqual(
    experimentReadiness({
      subject,
      draft: {
        ...DRAFT_OK,
        period: { start: "2025-01-01T10:00:00Z", end: "2025-01-01T10:00:00Z" },
      },
    }).blockerKeys,
    ["strategy_lab.experiment.blocker.period_order"],
  );
  // ...and a period longer than 3660 days (2000-01-01 → 2012-01-01 is ~4383).
  assert.deepEqual(period("2000-01-01", "2012-01-01"), [
    "strategy_lab.experiment.blocker.period_too_long",
  ]);
  // Just inside the bound is accepted, so the refusal is the bound and not a rounded guess.
  assert.deepEqual(period("2000-01-01", "2009-12-01"), []);
  assert.equal(EXPERIMENT_MAX_PERIOD_DAYS, 3660);
});

test("the request is composed only when the rule allows it", () => {
  const subject = { strategyId: "strategy-1", version: FROZEN };
  const body = experimentRequest({ subject, draft: DRAFT_OK });
  assert.ok(body);
  assert.equal(body.strategy_id, "strategy-1");
  assert.equal(body.base_strategy_version_id, "sv-1");
  assert.equal(body.name, "NBP sensitivity");
  // The engine's period is half-open over UTC instants, so a single-day period is not empty.
  assert.equal(body.evaluation_period_start_utc, "2025-01-01T00:00:00Z");
  assert.equal(body.evaluation_period_end_utc, "2025-12-31T23:59:59Z");

  // An unready draft produces no body at all: a partial one would invent the facts the route
  // then refuses.
  assert.equal(
    experimentRequest({ subject: { strategyId: "strategy-1", version: DRAFT }, draft: DRAFT_OK }),
    null,
  );
  assert.equal(experimentRequest({ subject, draft: { ...DRAFT_OK, name: "   " } }), null);

  // A value that already carries a time is passed through rather than re-anchored.
  assert.equal(startOfDayUtc("2025-01-01T06:30:00Z"), "2025-01-01T06:30:00Z");
  assert.equal(endOfDayUtc("2025-01-01T06:30:00Z"), "2025-01-01T06:30:00Z");
  assert.equal(startOfDayUtc(""), "");
});

test("an experiment groups the runs it names, not the runs that merely happened", () => {
  const runs = [
    { run_id: "run-1" },
    { run_id: "run-2" },
    { run_id: "run-3" },
  ];
  const grouped = experiment({ run_ids: ["run-1", "run-3"] });

  assert.deepEqual(runsInExperiment(runs, grouped).map((run) => run.run_id), ["run-1", "run-3"]);
  assert.deepEqual(runsInExperiment(runs, null), []);
  // The count comes from the experiment's own ids, so a run the bounded history has not loaded is
  // still part of the group: "3 runs, 2 shown" is not "2 runs".
  const older = experiment({ run_ids: ["run-1", "run-older"] });
  assert.deepEqual(unloadedRunIds(older, runs), ["run-older"]);
  assert.deepEqual(unloadedRunIds(null, runs), []);
});

test("experiments are filtered by strategy and read their own period", () => {
  const mine = experiment({ experiment_id: "experiment-1", strategy_id: "strategy-1" });
  const other = experiment({ experiment_id: "experiment-2", strategy_id: "strategy-2" });

  assert.deepEqual(
    experimentsForStrategy([mine, other], "strategy-1").map((item) => item.experiment_id),
    ["experiment-1"],
  );
  assert.deepEqual(experimentsForStrategy([mine, other], null), []);
  assert.deepEqual(experimentPeriod(mine), {
    start: "2025-01-01T00:00:00Z",
    end: "2025-12-31T23:59:59Z",
  });
  // A payload without a period reports no period rather than inventing one.
  assert.deepEqual(experimentPeriod(experiment({ evaluation_period: {} })), { start: "", end: "" });
});

test("the panel uses the declared experiment and metadata calls, not ad-hoc ones", () => {
  const panel = readWebSource("components/strategy/StrategyBacktestWorkspace.tsx");
  const controller = readWebSource("app/model/useStrategyLab.ts");
  const design = readWebSource("components/strategy/StrategyDesignWorkspace.tsx");
  const identity = readWebSource("app/model/useStrategyIdentityMetadata.ts");

  // The three reads and the create call the client declared and nothing used.
  assert.match(controller, /apiClient\.createBacktestExperiment\(/);
  assert.match(controller, /apiClient\.backtestExperiments\(\)/);
  assert.match(controller, /apiClient\.strategyRegistryRun\(/);
  assert.match(controller, /apiClient\.updateStrategyMetadata\(/);

  // The panel gates the create action on the mirrored rule and never composes a body itself.
  assert.match(panel, /experimentReadiness\(\{/);
  assert.match(panel, /controller\.createExperiment\(experimentDraft\)/);
  assert.equal(panel.includes("apiClient."), false);
  assert.equal(panel.includes("/api/"), false);

  // The identity edit follows the same split: the hook holds what would be written and performs the
  // write through the controller; the panel renders the fields and reports the verdict it is handed,
  // which is the property the workspace's own test holds every panel to.
  assert.match(identity, /controller\.updateStrategyMetadata\(/);
  assert.match(design, /void identity\.save\(\)/);
  assert.match(design, /disabled=\{!identity\.canSave \|\| identity\.busy\}/);
  assert.equal(design.includes("useState"), false);
  assert.ok(EXPERIMENT_NAME_MAX_LENGTH === 256);
});

test("the experiment vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  // Every key the rule can emit, plus the ones the panel renders.
  const keys = [
    "strategy_lab.experiments",
    "strategy_lab.experiments_note",
    "strategy_lab.experiment.create",
    "strategy_lab.experiment.selected",
    "strategy_lab.experiment.open_older_run",
    "strategy_lab.identity_actions",
    "strategy_lab.identity_actions_note",
    "strategy_lab.metadata.save",
  ];
  for (const blocker of [
    "no_strategy",
    "no_version",
    "version_not_frozen",
    "name_required",
    "name_too_long",
    "hypothesis_too_long",
    "period_required",
    "period_order",
    "period_too_long",
  ]) {
    keys.push(`strategy_lab.experiment.blocker.${blocker}`);
  }
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});
