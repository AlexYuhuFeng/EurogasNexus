/**
 * Per-leg evidence declarations in the Strategy Design draft (CR-04).
 *
 * The declaration is what the target-aware engine/2 selects evidence against.
 * This surface only edits, validates and round-trips it: no target is inferred
 * from a series name, an unset leg declares nothing, and a declaration this
 * form cannot read is preserved rather than rewritten. Both supported bases
 * (a fixed explicit UTC interval and a rolling gas day with an explicit
 * calendar and 0/1 offset) round-trip; month/quarter rolls are not offered.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  DEFAULT_STRATEGY_FORM,
  STRATEGY_EVIDENCE_LEGS,
  emptyEvidenceDeclaration,
  strategyDraftBody,
  strategyDraftValidation,
  strategyEvidenceBlocker,
  strategyEvidenceTargets,
  strategyFormFromVersion as readStrategyFormFromVersion,
  utcIsoFromInput,
  type StrategyDesignFormState,
} from "../src/app/model/strategyDraftModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function form(overrides: Partial<StrategyDesignFormState> = {}): StrategyDesignFormState {
  return { ...DEFAULT_STRATEGY_FORM, name: "OCM vs DA", resourceId: "explicit-test-resource", resourceName: "Test resource", resourceQuantity: "100", resourceCost: "20", ...overrides };
}

// Stored evidence fixtures explicitly supply a resource, so these tests isolate
// evidence projection rather than relying on fabricated production defaults.
function strategyFormFromVersion(definition?: Record<string, unknown>) {
  return readStrategyFormFromVersion(definition ? {
    resource_contexts: [{ resource_id: "explicit-test-resource", resource_name: "Test resource",
      available_quantity_mwh_per_day: 100, all_in_cost_gbp_mwh: 20 }],
    ...definition,
  } : definition);
}

function declaredLeg(overrides: Partial<ReturnType<typeof emptyEvidenceDeclaration>> = {}) {
  return {
    ...emptyEvidenceDeclaration(),
    enabled: true,
    role: "DELIVERY_PRICE",
    hub: "NBP",
    tenor: "day-ahead",
    priceBasis: "MID",
    deliveryStartUtc: "2026-10-01T05:00",
    deliveryEndUtc: "2026-10-02T05:00",
    ...overrides,
  };
}

function component(formState: StrategyDesignFormState): Record<string, unknown> {
  const body = strategyDraftBody(formState);
  return body.definition.components?.[0] as unknown as Record<string, unknown>;
}

test("multi-component definitions cannot be silently collapsed on save", () => {
  const built = component(form());
  const restored = strategyFormFromVersion({ components: [built, {...built, component_id: "other"}] });
  assert.equal(strategyEvidenceBlocker(restored), "strategy_lab.blocker.unsupported_definition");
});

test("fork delegates the complete frozen definition to the server", () => {
  const source = readWebSource("app/model/useStrategyDesignDraft.ts");
  assert.match(source, /forkStrategyVersion\(version.strategy_version_id, \{\}\)/);
});

test("an unset declaration writes no evidence_targets field at all", () => {
  const built = component(form());

  assert.equal("evidence_targets" in built, false);
  assert.equal(strategyEvidenceTargets(form()), null);
});

test("an opted-in leg declares the typed target from its existing names", () => {
  const targets = strategyEvidenceTargets(
    form({ dayAheadNames: "SAP, SAP_ALT", dayAheadEvidence: declaredLeg() }),
  );

  assert.deepEqual(targets, [
    {
      leg_id: "day_ahead",
      price_names: ["SAP", "SAP_ALT"],
      role: "DELIVERY_PRICE",
      hub: "NBP",
      tenor: "day-ahead",
      price_basis: "MID",
      target_basis: "EXPLICIT_INTERVAL",
      delivery_start_utc: "2026-10-01T05:00:00Z",
      delivery_end_utc: "2026-10-02T05:00:00Z",
    },
  ]);
});

test("a reference level declares its validity interval with the same endpoints", () => {
  const targets = strategyEvidenceTargets(
    form({ dayAheadEvidence: declaredLeg({ role: "REFERENCE_LEVEL" }) }),
  );

  assert.equal(targets?.[0].role, "REFERENCE_LEVEL");
  assert.equal(targets?.[0].delivery_start_utc, "2026-10-01T05:00:00Z");
  assert.equal(targets?.[0].target_basis, "EXPLICIT_INTERVAL");
});

test("a UTC wall clock round-trips through the declaration and back into the form", () => {
  const stored = {
    strategy_name: "Restored",
    components: [
      {
        component_id: "ocm-da-1",
        component_type: "OCM_VS_DAY_AHEAD",
        hubs: ["NBP"],
        extension_json: {
          day_ahead_price_names: ["SAP"],
          intraday_price_names: ["ICE_OCM"],
        },
        evidence_targets: [
          {
            leg_id: "day_ahead",
            price_names: ["SAP"],
            role: "DELIVERY_PRICE",
            hub: "NBP",
            tenor: "day-ahead",
            price_basis: "MID",
            target_basis: "EXPLICIT_INTERVAL",
            delivery_start_utc: "2026-10-01T05:00:00Z",
            delivery_end_utc: "2026-10-02T05:00:00Z",
          },
        ],
      },
    ],
  };

  const restored = strategyFormFromVersion(stored);

  assert.equal(restored.dayAheadEvidence.enabled, true);
  assert.equal(restored.dayAheadEvidence.deliveryStartUtc, "2026-10-01T05:00");
  assert.equal(restored.dayAheadEvidence.role, "DELIVERY_PRICE");
  assert.equal(restored.intradayEvidence.enabled, false);
  assert.equal(restored.evidenceRedeclarationRequired, false);

  // Read -> write is stable: the same declaration comes back out.
  assert.deepEqual(strategyEvidenceTargets(restored), [
    {
      leg_id: "day_ahead",
      price_names: ["SAP"],
      role: "DELIVERY_PRICE",
      hub: "NBP",
      tenor: "day-ahead",
      price_basis: "MID",
      target_basis: "EXPLICIT_INTERVAL",
      delivery_start_utc: "2026-10-01T05:00:00Z",
      delivery_end_utc: "2026-10-02T05:00:00Z",
    },
  ]);

  // A fork carries the declaration rather than dropping it.
  assert.deepEqual(component(restored).evidence_targets, strategyEvidenceTargets(restored));
});

test("a declaration whose price names moved is preserved instead of silently re-based", () => {
  const restored = strategyFormFromVersion({
    strategy_name: "Moved names",
    components: [
      {
        component_type: "OCM_VS_DAY_AHEAD",
        extension_json: {
          day_ahead_price_names: ["SAP_V2"],
          intraday_price_names: ["ICE_OCM"],
        },
        evidence_targets: [
          {
            leg_id: "day_ahead",
            price_names: ["SAP"],
            role: "DELIVERY_PRICE",
            hub: "NBP",
            tenor: "day-ahead",
            price_basis: "MID",
            target_basis: "EXPLICIT_INTERVAL",
            delivery_start_utc: "2026-10-01T05:00:00Z",
            delivery_end_utc: "2026-10-02T05:00:00Z",
          },
        ],
      },
    ],
  });

  // It cannot be rebuilt honestly, so the leg is not claimed as declared...
  assert.equal(restored.dayAheadEvidence.enabled, false);
  // ...but it is not discarded either: it is preserved verbatim, and saving is
  // refused with a reason rather than rewriting what it said.
  assert.equal(restored.preservedEvidenceTargets.length, 1);
  assert.deepEqual(
    (restored.preservedEvidenceTargets[0] as Record<string, unknown>).price_names,
    ["SAP"],
  );
  assert.equal(restored.evidenceRedeclarationRequired, true);
  assert.equal(
    strategyEvidenceBlocker(restored),
    "strategy_lab.blocker.evidence_redeclare",
  );
  assert.deepEqual(strategyDraftValidation(restored).blockerKeys, [
    "strategy_lab.blocker.evidence_redeclare",
  ]);
});

test("a target declared for another leg is carried through verbatim", () => {
  const extra = {
    leg_id: "intraday",
    price_names: ["ICE_OCM"],
    role: "REFERENCE_LEVEL",
    hub: "NBP",
    tenor: "within-day",
    price_basis: "ASSESSMENT",
    target_basis: "EXPLICIT_INTERVAL",
    delivery_start_utc: "2026-09-01T05:00:00Z",
    delivery_end_utc: "2026-10-01T05:00:00Z",
  };
  const restored = strategyFormFromVersion({
    components: [
      {
        component_type: "OCM_VS_DAY_AHEAD",
        extension_json: {
          day_ahead_price_names: ["SAP"],
          intraday_price_names: ["ICE_OCM"],
        },
        evidence_targets: [extra],
      },
    ],
  });

  // intraday is an editable leg whose names match, so it is editable state...
  assert.equal(restored.intradayEvidence.enabled, true);
  assert.equal(restored.intradayEvidence.priceBasis, "ASSESSMENT");
  assert.equal(restored.evidenceRedeclarationRequired, false);

  // ...and re-saving produces the same declaration, not a rewritten one.
  assert.deepEqual(strategyEvidenceTargets(restored), [
    {
      leg_id: "intraday",
      price_names: ["ICE_OCM"],
      role: "REFERENCE_LEVEL",
      hub: "NBP",
      tenor: "within-day",
      price_basis: "ASSESSMENT",
      target_basis: "EXPLICIT_INTERVAL",
      delivery_start_utc: "2026-09-01T05:00:00Z",
      delivery_end_utc: "2026-10-01T05:00:00Z",
    },
  ]);
});

test("an unreadable stored declaration disables saving rather than being guessed", () => {
  const restored = strategyFormFromVersion({
    strategy_name: "Unreadable basis",
    components: [
      {
        component_type: "OCM_VS_DAY_AHEAD",
        extension_json: {
          day_ahead_price_names: ["SAP"],
          intraday_price_names: ["ICE_OCM"],
        },
        evidence_targets: [
          {
            leg_id: "day_ahead",
            price_names: ["SAP"],
            role: "DELIVERY_PRICE",
            hub: "NBP",
            tenor: "day-ahead",
            price_basis: "MID",
            // A future basis this slice refuses: not editable here.
            target_basis: "ROLLING_GAS_DAY",
            delivery_start_utc: "2026-10-01T05:00:00Z",
            delivery_end_utc: "2026-10-02T05:00:00Z",
          },
        ],
      },
    ],
  });

  assert.equal(restored.evidenceRedeclarationRequired, true);
  assert.equal(restored.preservedEvidenceTargets.length, 1);
  assert.deepEqual(strategyDraftValidation(restored).blockerKeys, [
    "strategy_lab.blocker.evidence_redeclare",
  ]);
});

test("a stored declaration for a leg this surface does not edit is preserved, not blocked", () => {
  // A later-phase declaration (month-ahead) is carried through verbatim so a
  // fork keeps it; it does not make the rest of the draft unsaveable.
  const extra = {
    leg_id: "month_ahead",
    price_names: ["NBP_M1"],
    role: "REFERENCE_LEVEL",
    hub: "NBP",
    tenor: "month",
    price_basis: "ASSESSMENT",
    target_basis: "EXPLICIT_INTERVAL",
    delivery_start_utc: "2026-11-01T05:00:00Z",
    delivery_end_utc: "2026-12-01T05:00:00Z",
  };
  const restored = strategyFormFromVersion({
    components: [
      {
        component_type: "OCM_VS_DAY_AHEAD",
        extension_json: {
          day_ahead_price_names: ["SAP"],
          intraday_price_names: ["ICE_OCM"],
        },
        evidence_targets: [extra],
      },
    ],
  });

  assert.equal(restored.evidenceRedeclarationRequired, false);
  assert.deepEqual(restored.preservedEvidenceTargets, [extra]);
  assert.equal(strategyEvidenceBlocker(restored), null);
  assert.deepEqual(component(restored).evidence_targets, [extra]);
});

test("a leg left unset is not a blocker, so EVALUATION drafts stay saveable", () => {
  const validation = strategyDraftValidation(
    form({ transactionCostTreatment: "MODELED_COST", transactionCost: "0.2" }),
  );

  assert.deepEqual(validation.blockerKeys, []);
  assert.deepEqual(strategyDraftValidation(form({
    transactionCostTreatment: "MODELED_COST",
    transactionCost: "0.2",
    intradayEvidence: declaredLeg(),
  })).blockerKeys, []);
});

test("an opted-in leg that is incomplete blocks the save with a specific key", () => {
  const clean = { transactionCostTreatment: "MODELED_COST", transactionCost: "0.2" };
  const cases: Array<[Partial<ReturnType<typeof emptyEvidenceDeclaration>>, string]> = [
    [{ role: "" }, "strategy_lab.blocker.evidence_role"],
    [{ hub: "" }, "strategy_lab.blocker.evidence_fields"],
    [{ tenor: "  " }, "strategy_lab.blocker.evidence_fields"],
    [{ priceBasis: "" }, "strategy_lab.blocker.evidence_fields"],
    [{ deliveryStartUtc: "" }, "strategy_lab.blocker.evidence_interval"],
    [{ deliveryEndUtc: "" }, "strategy_lab.blocker.evidence_interval"],
    [{ deliveryEndUtc: "2026-10-01T05:00" }, "strategy_lab.blocker.evidence_interval_order"],
    [{ deliveryEndUtc: "2026-09-30T05:00" }, "strategy_lab.blocker.evidence_interval_order"],
  ];

  for (const [override, key] of cases) {
    const blocked = strategyDraftValidation(
      form({ ...clean, dayAheadEvidence: declaredLeg(override) }),
    );
    assert.deepEqual(blocked.blockerKeys, [key], JSON.stringify(override));
  }
});

test("the UTC input conversion declares UTC rather than the browser zone", () => {
  assert.equal(utcIsoFromInput("2026-10-01T05:00"), "2026-10-01T05:00:00Z");
  assert.equal(utcIsoFromInput(""), null);
  assert.equal(utcIsoFromInput("not a time"), null);
});

test("a rolling gas-day declaration round-trips with its calendar and offset", () => {
  const rolling = declaredLeg({
    targetBasis: "GAS_DAY",
    calendarId: "EU-CAM-UTC-2025",
    gasDayOffset: "1",
    deliveryStartUtc: "",
    deliveryEndUtc: "",
  });
  const targets = strategyEvidenceTargets(form({ dayAheadEvidence: rolling }));

  assert.deepEqual(targets, [
    {
      leg_id: "day_ahead",
      price_names: ["SAP"],
      role: "DELIVERY_PRICE",
      hub: "NBP",
      tenor: "day-ahead",
      price_basis: "MID",
      target_basis: "GAS_DAY",
      calendar_id: "EU-CAM-UTC-2025",
      gas_day_offset: 1,
    },
  ]);
  // A rolling target carries no explicit endpoints; the interval is resolved by
  // the backend calendar at each decision.
  assert.equal("delivery_start_utc" in (targets?.[0] ?? {}), false);
  assert.equal("delivery_end_utc" in (targets?.[0] ?? {}), false);

  const restored = strategyFormFromVersion({
    components: [
      {
        component_type: "OCM_VS_DAY_AHEAD",
        extension_json: {
          day_ahead_price_names: ["SAP"],
          intraday_price_names: ["ICE_OCM"],
        },
        evidence_targets: targets,
      },
    ],
  });
  assert.equal(restored.dayAheadEvidence.enabled, true);
  assert.equal(restored.dayAheadEvidence.targetBasis, "GAS_DAY");
  assert.equal(restored.dayAheadEvidence.calendarId, "EU-CAM-UTC-2025");
  assert.equal(restored.dayAheadEvidence.gasDayOffset, "1");
  assert.deepEqual(strategyEvidenceTargets(restored), targets);
});

test("an explicit declaration never writes rolling calendar fields", () => {
  const target = (
    component(form({ dayAheadEvidence: declaredLeg() })).evidence_targets as Record<string, unknown>[]
  )[0];
  assert.equal("calendar_id" in target, false);
  assert.equal("gas_day_offset" in target, false);
});

test("rolling target fields are validated with specific blocker keys", () => {
  const clean = { transactionCostTreatment: "MODELED_COST", transactionCost: "0.2" };
  const cases: Array<[Partial<ReturnType<typeof emptyEvidenceDeclaration>>, string]> = [
    [{ targetBasis: "TENOR_ROLL" }, "strategy_lab.blocker.evidence_basis"],
    [
      { targetBasis: "GAS_DAY", calendarId: "EU-CAM-2025", gasDayOffset: "0" },
      "strategy_lab.blocker.evidence_calendar",
    ],
    [
      { targetBasis: "GAS_DAY", calendarId: "EU-CAM-UTC-2025", gasDayOffset: "2" },
      "strategy_lab.blocker.evidence_offset",
    ],
  ];

  for (const [override, key] of cases) {
    const declaration = declaredLeg({
      deliveryStartUtc: "",
      deliveryEndUtc: "",
      ...override,
    });
    const blocked = strategyDraftValidation(
      form({ ...clean, dayAheadEvidence: declaration }),
    );
    assert.deepEqual(blocked.blockerKeys, [key], JSON.stringify(override));
  }
});

test("the two leg fieldsets default to unset and are opt-in", () => {
  assert.equal(STRATEGY_EVIDENCE_LEGS.length, 2);
  assert.deepEqual(
    STRATEGY_EVIDENCE_LEGS.map((leg) => leg.legId),
    ["day_ahead", "intraday"],
  );
  for (const leg of STRATEGY_EVIDENCE_LEGS) {
    assert.equal(DEFAULT_STRATEGY_FORM[leg.stateKey].enabled, false);
  }
  assert.equal(strategyDraftValidation(form()).blockerKeys.includes("strategy_lab.blocker.evidence_role"), false);
});

test("the panel renders declarations, both bases and the supported/unsupported boundary", () => {
  const panel = readWebSource("components/strategy/StrategyDesignWorkspace.tsx");
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  assert.match(panel, /STRATEGY_EVIDENCE_LEGS\.map/);
  assert.match(panel, /draft\.setEvidenceField/);
  assert.match(panel, /strategy_lab\.evidence\.intro/);
  assert.match(panel, /strategy_lab\.evidence\.unsupported/);
  assert.match(panel, /STRATEGY_EVIDENCE_TARGET_BASES\.map/);
  assert.match(panel, /STRATEGY_GAS_DAY_CALENDARS/);
  assert.match(panel, /STRATEGY_GAS_DAY_OFFSETS/);
  for (const key of [
    "strategy_lab.evidence.title",
    "strategy_lab.evidence.intro",
    "strategy_lab.evidence.unsupported",
    "strategy_lab.evidence.opt_in",
    "strategy_lab.evidence.names_source",
    "strategy_lab.evidence.role",
    "strategy_lab.evidence.hub",
    "strategy_lab.evidence.tenor",
    "strategy_lab.evidence.price_basis",
    "strategy_lab.evidence.target_basis",
    "strategy_lab.evidence.basis_explicit_interval",
    "strategy_lab.evidence.basis_gas_day",
    "strategy_lab.evidence.calendar",
    "strategy_lab.evidence.offset",
    "strategy_lab.evidence.offset_current",
    "strategy_lab.evidence.offset_next",
    "strategy_lab.evidence.start_utc",
    "strategy_lab.evidence.end_utc",
    "strategy_lab.evidence.preserved",
    "strategy_lab.blocker.evidence_role",
    "strategy_lab.blocker.evidence_fields",
    "strategy_lab.blocker.evidence_basis",
    "strategy_lab.blocker.evidence_calendar",
    "strategy_lab.blocker.evidence_offset",
    "strategy_lab.blocker.evidence_interval",
    "strategy_lab.blocker.evidence_interval_order",
    "strategy_lab.blocker.evidence_redeclare",
    "strategy_lab.blocker.evidence_target_missing",
    "strategy_lab.data_coverage",
    "strategy_lab.evaluation_completion_help",
    "strategy_lab.evidence_diagnostics",
    "strategy_lab.evidence_diagnostics_distinct",
    "strategy_lab.evidence_diagnostics_reused",
    "strategy_lab.evidence_diagnostics_simulated",
  ]) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
  // The engine/2 capability is described, not the old "not implemented" state.
  assert.match(en["strategy_lab.evidence.intro"], /rolling gas day/i);
  assert.match(en["strategy_lab.evidence.unsupported"], /month and quarter/i);
  assert.equal(/not implemented yet/i.test(en["strategy_lab.evidence.intro"]), false);
  // Coverage is named honestly.
  assert.match(en["strategy_lab.data_coverage"], /Evaluation completion/);
});
