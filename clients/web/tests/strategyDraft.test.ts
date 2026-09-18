/**
 * Strategy draft rule tests (Architecture V2 Wave 9, action geography).
 *
 * Saving a draft is a `persist` consequence, so it belongs in the Design task's primary slot. That
 * was impossible while the draft lived in the panel, so the draft and its rule moved into
 * `app/model/strategyDraftModel.ts` and the workspace owns them. These tests pin the rule itself -
 * which had no test before, because it existed only as a `useMemo` inside a component - and the
 * two acts the geography deliberately keeps *out* of the primary slot.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  DEFAULT_STRATEGY_FORM,
  strategyDraftBody,
  strategyDraftName,
  strategyDraftReadiness,
  strategyDraftValidation,
  strategyFormFromVersion,
  strategyVersionEditable,
  strategyVersionFrozen,
  type StrategyDesignFormState,
} from "../src/app/model/strategyDraftModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function form(overrides: Partial<StrategyDesignFormState> = {}): StrategyDesignFormState {
  return { ...DEFAULT_STRATEGY_FORM, name: "OCM vs DA", ...overrides };
}

/**
 * A draft with nothing to report.
 *
 * The default form carries an unmodeled transaction cost, which is a *warning* by design - the run
 * is still a real measurement, it just excludes a cost the operator has not modeled - so a draft
 * with no warnings at all models it.
 */
function cleanForm(overrides: Partial<StrategyDesignFormState> = {}): StrategyDesignFormState {
  return form({ transactionCostTreatment: "MODELED_COST", transactionCost: "0.25", ...overrides });
}

function readiness(overrides: Partial<Parameters<typeof strategyDraftReadiness>[0]> = {}) {
  return strategyDraftReadiness({
    validation: strategyDraftValidation(cleanForm()),
    busy: false,
    frozen: false,
    ...overrides,
  });
}

test("a complete draft reports nothing at all and may be saved", () => {
  assert.deepEqual(strategyDraftValidation(cleanForm()), { blockerKeys: [], warningKeys: [] });
  assert.deepEqual(readiness(), { canSave: true, blockerKeys: [], firstBlockerKey: null });
});

test("an unmodeled cost is disclosed rather than refused", () => {
  // The default form is exactly this case: a run that excludes a cost the operator has not
  // modeled is honest as long as it says so.
  const disclosed = strategyDraftValidation(form({ transactionCostTreatment: "UNAVAILABLE" }));
  assert.deepEqual(disclosed.blockerKeys, []);
  assert.deepEqual(disclosed.warningKeys, ["strategy_lab.warning.transaction_cost_unavailable"]);
  assert.equal(strategyDraftReadiness({ validation: disclosed, busy: false, frozen: false }).canSave, true);
});

test("the blockers are the ones this surface owns, as keys rather than copy", () => {
  assert.deepEqual(strategyDraftValidation(form({ name: "   " })).blockerKeys, [
    "strategy_lab.blocker.name",
  ]);
  assert.deepEqual(strategyDraftValidation(form({ dayAheadNames: " , " })).blockerKeys, [
    "strategy_lab.blocker.day_ahead",
  ]);
  assert.deepEqual(strategyDraftValidation(form({ intradayNames: "" })).blockerKeys, [
    "strategy_lab.blocker.intraday",
  ]);
  // A resource that cannot be evaluated is not a resource.
  for (const quantity of ["", "0", "-5", "abc"]) {
    assert.ok(
      strategyDraftValidation(form({ resourceQuantity: quantity })).blockerKeys.includes(
        "strategy_lab.blocker.resource",
      ),
      quantity,
    );
  }
  assert.ok(
    strategyDraftValidation(form({ resourceCost: "0" })).blockerKeys.includes(
      "strategy_lab.blocker.resource",
    ),
  );
});

test("a modeled cost must parse, and an unavailable one is a warning rather than a blocker", () => {
  // A modeled cost that does not parse would change the backtest rather than the request.
  assert.deepEqual(
    strategyDraftValidation(
      form({ transactionCostTreatment: "MODELED_COST", transactionCost: "abc" }),
    ).blockerKeys,
    ["strategy_lab.blocker.transaction_cost"],
  );
  assert.deepEqual(
    strategyDraftValidation(
      form({ transactionCostTreatment: "MODELED_COST", transactionCost: "0.5" }),
    ).blockerKeys,
    [],
  );
  // An unmodeled cost is disclosed, not refused: the run is still a real measurement. A modeled
  // one that parses is clean, and the two warnings are independent so both are reported.
  assert.deepEqual(
    strategyDraftValidation(cleanForm()).warningKeys,
    [],
  );
  assert.deepEqual(
    strategyDraftValidation(cleanForm({ missingDataPolicy: "CARRY_FORWARD_WITH_MAX_AGE" }))
      .warningKeys,
    ["strategy_lab.warning.carry_forward"],
  );
  assert.deepEqual(
    strategyDraftValidation(
      form({
        transactionCostTreatment: "UNAVAILABLE",
        missingDataPolicy: "CARRY_FORWARD_WITH_MAX_AGE",
      }),
    ).warningKeys,
    [
      "strategy_lab.warning.transaction_cost_unavailable",
      "strategy_lab.warning.carry_forward",
    ],
  );
});

test("a frozen version is not this act, and a request in flight blocks the next one", () => {
  // Freezing is a `lifecycle` act: the surface forks a new version instead of writing a frozen
  // one, so a frozen draft reports *why* rather than pretending to be an incomplete form.
  const frozen = readiness({ frozen: true });
  assert.equal(frozen.canSave, false);
  assert.deepEqual(frozen.blockerKeys, ["strategy_lab.blocker.frozen_edit"]);

  assert.deepEqual(readiness({ busy: true }).blockerKeys, ["strategy_lab.blocker.in_flight"]);
  // A real precondition is reported before the transient one.
  assert.deepEqual(readiness({ frozen: true, busy: true }).blockerKeys, [
    "strategy_lab.blocker.frozen_edit",
    "strategy_lab.blocker.in_flight",
  ]);
  assert.equal(strategyVersionFrozen({ status: "FROZEN" } as never), true);
  assert.equal(strategyVersionFrozen({ status: "DRAFT" } as never), false);
  assert.equal(strategyVersionEditable({ status: "DRAFT" } as never), true);
  assert.equal(strategyVersionEditable(null), false);
});

test("the request body carries the form and nothing invented", () => {
  const body = strategyDraftBody(
    form({
      name: "OCM vs DA",
      hubs: "NBP, TTF",
      transactionCostTreatment: "MODELED_COST",
      transactionCost: "0.4",
      requireTsoAccess: true,
    }),
  );

  assert.equal(body.strategy_name, "OCM vs DA");
  assert.equal(body.run_mode, "BACKTEST");
  assert.deepEqual(body.definition.data_requirements, { hubs: ["NBP", "TTF"] });
  assert.deepEqual(body.definition.components[0].hubs, ["NBP", "TTF"]);
  assert.deepEqual(body.definition.risk_controls, {
    max_ocm_allocation_pct: 80,
    min_day_ahead_allocation_pct: 10,
    require_tso_access: true,
  });
  assert.deepEqual(body.definition.economic_assumptions.cost_components, [
    { code: "TRANSACTION_COST", treatment: "MODELED_COST", amount_gbp_mwh: 0.4 },
    { code: "SLIPPAGE", treatment: "UNAVAILABLE", amount_gbp_mwh: null },
  ]);
  assert.equal(body.resource_contexts?.[0].resource_id, "res-1");
  // The name a first save uses is decided once, here, rather than at the call site.
  assert.equal(strategyDraftName(form({ name: "  " })), "Untitled strategy");
});

test("a stored version reads back into the form, and an empty definition stays default", () => {
  assert.deepEqual(strategyFormFromVersion(undefined), DEFAULT_STRATEGY_FORM);
  const restored = strategyFormFromVersion({
    strategy_name: "Restored",
    hypothesis: "h",
    components: [{ hubs: ["NBP"], extension_json: { weight: 2, target_bar_minutes: 15 } }],
    risk_controls: { max_ocm_allocation_pct: 50, require_tso_access: true },
    resource_contexts: [{ resource_id: "res-9", available_quantity_mwh_per_day: 250 }],
  });
  assert.equal(restored.name, "Restored");
  assert.equal(restored.hubs, "NBP");
  assert.equal(restored.weight, "2");
  assert.equal(restored.barMinutes, "15");
  assert.equal(restored.maxOcm, "50");
  assert.equal(restored.requireTsoAccess, true);
  assert.equal(restored.resourceId, "res-9");
  assert.equal(restored.resourceQuantity, "250");
});

test("the workspace hosts the save and the panel keeps only the guarded acts", () => {
  const workspace = readWebSource("components/strategy/StrategyLabWorkspace.tsx");
  const panel = readWebSource("components/strategy/StrategyDesignWorkspace.tsx");
  const hook = readWebSource("app/model/useStrategyDesignDraft.ts");

  // The draft and its rule live with the action.
  assert.match(hook, /export function useStrategyDesignDraft\(/);
  assert.match(hook, /const readiness = strategyDraftReadiness\(\{ validation, busy, frozen \}\);/);
  assert.match(hook, /if \(!readiness\.canSave\) return;/);
  assert.match(hook, /const body = strategyDraftBody\(form\);/);
  assert.match(workspace, /const designDraft = useStrategyDesignDraft\(\{ controller, selection, t \}\);/);
  assert.match(workspace, /controller\.task === "design" && !designDraft\.frozen \? \(/);
  assert.match(workspace, /onClick=\{\(\) => void designDraft\.saveDraft\(\)\}/);
  assert.match(workspace, /draft=\{designDraft\}/);

  // The panel no longer owns or writes the draft; it renders it and reports the verdict.
  assert.equal(panel.includes("useState"), false);
  assert.equal(panel.includes("apiClient"), false);
  assert.equal(panel.includes("strategy_lab.save_draft"), false);
  assert.equal(panel.includes("const buildBody"), false);
  assert.match(panel, /const \{ form, setField: set, validation \} = draft;/);
  assert.match(panel, /\{validation\.blockerKeys\.map\(\(key\) => <div key=\{key\}>BLOCKER: \{t\(key\)\}<\/div>\)\}/);

  // The two `lifecycle` acts stay bounded, with the reason stated where they sit.
  assert.match(panel, /className="strategy-version-actions"/);
  assert.match(panel, /t\("strategy_lab\.version_actions_note"\)/);
  assert.match(panel, /onClick=\{\(\) => void draft\.freezeVersion\(\)\}/);
  assert.match(panel, /onClick=\{\(\) => void draft\.createNewVersion\(\)\}/);
});

test("every new strategy-draft string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  for (const key of [
    "strategy_lab.save_draft",
    "strategy_lab.save_draft_hint",
    "strategy_lab.blocker.frozen_edit",
    "strategy_lab.blocker.in_flight",
    "strategy_lab.version_actions",
    "strategy_lab.version_actions_note",
  ]) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
