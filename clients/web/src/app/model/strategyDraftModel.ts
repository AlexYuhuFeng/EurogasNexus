/**
 * Strategy draft model (Architecture V2 Wave 9, action geography).
 *
 * Saving a strategy draft is a `persist` consequence, so it belongs in the Design task's primary
 * slot rather than in the panel that edits the form. That was impossible while the *draft itself*
 * lived in the panel - about twenty-five form fields, their validation and the request builder -
 * so the draft moved here (state and rule) and the workspace that hosts the action owns it.
 *
 * The rule returns **translation keys**, not copy, so the panel renders the verdict it was handed
 * and cannot disagree with the header about whether the draft may be written.
 *
 * The other two acts on this surface are deliberately *not* here: freezing a version and creating
 * a new one are `lifecycle` consequences, which the geography keeps as bounded actions next to the
 * version they change (`requiresDeliberateStep("lifecycle")` is true), never in the primary slot.
 */

import type { StrategyVersionCreateInputDTO, StrategyVersionDTO } from "../../api/client.ts";

export interface StrategyEvidenceDeclarationState {
  /** The operator opted this leg in; unset is the default and declares nothing. */
  enabled: boolean;
  role: string;
  hub: string;
  tenor: string;
  priceBasis: string;
  /** `EXPLICIT_INTERVAL` (fixed UTC endpoints) or `GAS_DAY` (rolling gas day). */
  targetBasis: string;
  /** GAS_DAY only: the explicit canonical calendar id. */
  calendarId: string;
  /** GAS_DAY only: `"0"` current gas day or `"1"` next gas day. */
  gasDayOffset: string;
  /** EXPLICIT_INTERVAL only: UTC wall-clock endpoints in `datetime-local` form. */
  deliveryStartUtc: string;
  deliveryEndUtc: string;
}

export type StrategyEvidenceTargetRole = "DELIVERY_PRICE" | "REFERENCE_LEVEL";

export interface StrategyEvidenceTargetDeclaration {
  leg_id: string;
  price_names: string[];
  role: string;
  hub: string;
  tenor: string;
  price_basis: string;
  target_basis: string;
  delivery_start_utc?: string;
  delivery_end_utc?: string;
  calendar_id?: string;
  gas_day_offset?: number;
}

/**
 * A leg this surface can edit.
 *
 * `priceNameKey` is the key inside the component's existing `extension_json`
 * that already lists the leg's price names, so the declaration is built from
 * the names the strategy actually uses rather than a renamed copy.
 * `stateKey` names the matching field on the form.
 */
export interface StrategyEvidenceLegSpec {
  readonly legId: string;
  readonly priceNameKey: string;
  readonly stateKey: "dayAheadEvidence" | "intradayEvidence";
  readonly titleKey: string;
}

/** The OCM vs day-ahead component's two price legs, in declaration order. */
export const STRATEGY_EVIDENCE_LEGS: readonly StrategyEvidenceLegSpec[] = [
  {
    legId: "day_ahead",
    priceNameKey: "day_ahead_price_names",
    stateKey: "dayAheadEvidence",
    titleKey: "strategy_lab.day_ahead_names",
  },
  {
    legId: "intraday",
    priceNameKey: "intraday_price_names",
    stateKey: "intradayEvidence",
    titleKey: "strategy_lab.intraday_names",
  },
];

const STRATEGY_EVIDENCE_ROLES: readonly string[] = ["DELIVERY_PRICE", "REFERENCE_LEVEL"];
/** The target bases this surface can declare. Month/quarter rolls are not implemented. */
export const STRATEGY_EVIDENCE_TARGET_BASES: readonly string[] = [
  "EXPLICIT_INTERVAL",
  "GAS_DAY",
];
/** The only canonical calendar allowed for a newly declared rolling target. */
export const STRATEGY_GAS_DAY_CALENDARS: readonly string[] = ["EU-CAM-UTC-2025"];
export const STRATEGY_GAS_DAY_OFFSETS: readonly string[] = ["0", "1"];
const STRATEGY_EXPLICIT_BASIS = "EXPLICIT_INTERVAL";
const STRATEGY_GAS_DAY_BASIS = "GAS_DAY";

export interface StrategyDesignFormState {
  unsupportedDefinition: boolean;
  name: string;
  description: string;
  hypothesis: string;
  hubs: string;
  dayAheadNames: string;
  intradayNames: string;
  dayAheadEvidence: StrategyEvidenceDeclarationState;
  intradayEvidence: StrategyEvidenceDeclarationState;
  /**
   * Declarations the current form cannot edit, kept verbatim so that saving a
   * forked draft never silently discards semantics it does not understand.
   */
  preservedEvidenceTargets: (StrategyEvidenceTargetDeclaration | Record<string, unknown>)[];
  /**
   * A preserved declaration collides with a leg this surface edits, so its
   * stored price names no longer match; the operator must re-declare it.
   */
  evidenceRedeclarationRequired: boolean;
  weight: string;
  positiveThreshold: string;
  negativeThreshold: string;
  windowStart: string;
  windowEnd: string;
  barMinutes: string;
  maxOcm: string;
  minDayAhead: string;
  requireTsoAccess: boolean;
  fillPricePolicy: string;
  missingDataPolicy: string;
  transactionCostTreatment: string;
  transactionCost: string;
  slippageTreatment: string;
  slippage: string;
  resourceId: string;
  resourceName: string;
  resourceQuantity: string;
  resourceCost: string;
  resourceBasisBlocked: boolean;
}

/** One leg's empty declaration state, shared by the defaults and the reader. */
export function emptyEvidenceDeclaration(): StrategyEvidenceDeclarationState {
  return {
    enabled: false,
    role: "",
    hub: "",
    tenor: "",
    priceBasis: "",
    targetBasis: STRATEGY_EXPLICIT_BASIS,
    calendarId: STRATEGY_GAS_DAY_CALENDARS[0],
    gasDayOffset: "0",
    deliveryStartUtc: "",
    deliveryEndUtc: "",
  };
}

export const DEFAULT_STRATEGY_FORM: StrategyDesignFormState = {
  unsupportedDefinition: false,
  name: "",
  description: "",
  hypothesis: "",
  hubs: "NBP",
  dayAheadNames: "SAP",
  intradayNames: "ICE_OCM",
  dayAheadEvidence: emptyEvidenceDeclaration(),
  intradayEvidence: emptyEvidenceDeclaration(),
  preservedEvidenceTargets: [],
  evidenceRedeclarationRequired: false,
  weight: "1.0",
  positiveThreshold: "0.0",
  negativeThreshold: "0.0",
  windowStart: "05:00",
  windowEnd: "05:30",
  barMinutes: "5",
  maxOcm: "80.0",
  minDayAhead: "10.0",
  requireTsoAccess: false,
  fillPricePolicy: "NEXT_ELIGIBLE",
  missingDataPolicy: "FAIL",
  transactionCostTreatment: "UNAVAILABLE",
  transactionCost: "",
  slippageTreatment: "UNAVAILABLE",
  slippage: "",
  resourceId: "",
  resourceName: "",
  resourceQuantity: "",
  resourceCost: "",
  resourceBasisBlocked: false,
};

/**
 * The stored declaration for one editable leg, or `null` when the current form
 * cannot edit it safely.
 *
 * A declaration is only editable when this surface can rebuild it without
 * losing meaning: a known leg, a supported target basis, a known role and the
 * price names the leg already uses. Anything else is preserved verbatim
 * instead of being rewritten into something the operator did not declare.
 */
function evidenceDeclarationFromStored(
  stored: unknown,
  leg: StrategyEvidenceLegSpec,
  currentNames: readonly string[],
): StrategyEvidenceDeclarationState | null {
  if (!stored || typeof stored !== "object") return null;
  const target = stored as Record<string, unknown>;
  if (String(target.leg_id ?? "") !== leg.legId) return null;
  const role = String(target.role ?? "");
  if (!STRATEGY_EVIDENCE_ROLES.includes(role)) return null;
  const basis = String(target.target_basis ?? "");
  if (!STRATEGY_EVIDENCE_TARGET_BASES.includes(basis)) return null;
  const names = Array.isArray(target.price_names)
    ? (target.price_names as unknown[]).map((name) => String(name))
    : [];
  if (names.length === 0) return null;
  if ([...names].sort().join("\u0000") !== [...currentNames].sort().join("\u0000")) return null;
  const base: StrategyEvidenceDeclarationState = {
    enabled: true,
    role,
    hub: String(target.hub ?? ""),
    tenor: String(target.tenor ?? ""),
    priceBasis: String(target.price_basis ?? ""),
    targetBasis: basis,
    calendarId: STRATEGY_GAS_DAY_CALENDARS[0],
    gasDayOffset: "0",
    deliveryStartUtc: "",
    deliveryEndUtc: "",
  };
  if (basis === STRATEGY_GAS_DAY_BASIS) {
    // A rolling target is editable only when its explicit canonical calendar
    // and 0/1 offset are both readable; anything else is preserved verbatim.
    const calendar = String(target.calendar_id ?? "");
    const offset = target.gas_day_offset;
    if (!STRATEGY_GAS_DAY_CALENDARS.includes(calendar)) return null;
    if (offset !== 0 && offset !== 1) return null;
    return { ...base, calendarId: calendar, gasDayOffset: String(offset) };
  }
  // A naive stored timestamp is not the aware UTC instant the domain requires,
  // so it cannot be shown as an editable UTC wall clock either.
  const start = storedUtcWallClock(target.delivery_start_utc);
  const end = storedUtcWallClock(target.delivery_end_utc);
  if (!start || !end) return null;
  return { ...base, deliveryStartUtc: start, deliveryEndUtc: end };
}

/** Read an aware stored ISO-8601 instant as a UTC wall clock, or `null`. */
function storedUtcWallClock(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (!/(Z|[+-]\d{2}:?\d{2})$/.test(value)) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  // The editor has minute precision: do not truncate existing instants.
  if (parsed.getUTCSeconds() !== 0 || parsed.getUTCMilliseconds() !== 0) return null;
  return parsed.toISOString().slice(0, 16);
}

/** Read a stored ISO-8601 instant into the UTC wall clock a datetime-local input holds. */
export function utcInputFromIso(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 16);
}

/**
 * Turn a `datetime-local` wall clock into the UTC instant it denotes.
 *
 * The surface labels these inputs UTC, so the value is *declared* UTC rather
 * than reinterpreted in the browser's local zone.
 */
export function utcIsoFromInput(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().replace(".000Z", "Z");
}

/** Read a stored version's definition back into the form, defaulting anything it omits. */
export function strategyFormFromVersion(
  definition: Record<string, unknown> | undefined,
): StrategyDesignFormState {
  if (!definition) return DEFAULT_STRATEGY_FORM;
  const component = Array.isArray(definition.components)
    ? (definition.components[0] as Record<string, unknown>)
    : null;
  const extension = (component?.extension_json as Record<string, unknown>) ?? {};
  const risk = (definition.risk_controls as Record<string, unknown>) ?? {};
  const resources = Array.isArray(definition.resource_contexts)
    ? (definition.resource_contexts[0] as Record<string, unknown>)
    : null;
  const dayAheadNames = Array.isArray(extension.day_ahead_price_names)
    ? (extension.day_ahead_price_names as string[]).join(", ")
    : "SAP";
  const intradayNames = Array.isArray(extension.intraday_price_names)
    ? (extension.intraday_price_names as string[]).join(", ")
    : "ICE_OCM";
  const namesByLeg: Record<string, readonly string[]> = {
    day_ahead: strategyCsv(dayAheadNames),
    intraday: strategyCsv(intradayNames),
  };
  const storedTargets = readStoredEvidenceTargets(component?.evidence_targets);
  const declarations: Record<string, StrategyEvidenceDeclarationState | null> = {
    dayAheadEvidence: null,
    intradayEvidence: null,
  };
  // A declaration is only "consumed" by the form when it was actually rebuilt
  // into editable state; anything else is preserved verbatim below.
  const editableLegIds = new Set<string>();
  for (const leg of STRATEGY_EVIDENCE_LEGS) {
    const match = storedTargets.find(
      (target) => String((target as Record<string, unknown>).leg_id ?? "") === leg.legId,
    );
    if (!match) continue;
    const declaration = evidenceDeclarationFromStored(match, leg, namesByLeg[leg.legId] ?? []);
    declarations[leg.stateKey] = declaration;
    if (declaration) editableLegIds.add(leg.legId);
  }
  const preserved = storedTargets.filter(
    (target): target is Record<string, unknown> =>
      typeof target === "object" &&
      target !== null &&
      !editableLegIds.has(String((target as Record<string, unknown>).leg_id ?? "")),
  );
  // A stored declaration for a leg this surface edits that could not be rebuilt
  // (a future basis, a moved price name, an unreadable timestamp) must not be
  // silently re-based: the operator re-declares it on a fork.
  const redeclarationRequired = STRATEGY_EVIDENCE_LEGS.some((leg) => {
    if (declarations[leg.stateKey] !== null) return false;
    return storedTargets.some(
      (target) => String((target as Record<string, unknown>).leg_id ?? "") === leg.legId,
    );
  });
  return {
    ...DEFAULT_STRATEGY_FORM,
    unsupportedDefinition: (Array.isArray(definition.components) && definition.components.length !== 1)
      || (component != null && component.component_type !== "OCM_VS_DAY_AHEAD"),
    name: String(definition.strategy_name ?? ""),
    hypothesis: String(definition.hypothesis ?? ""),
    hubs: Array.isArray(component?.hubs) ? (component?.hubs as string[]).join(", ") : "NBP",
    dayAheadNames,
    intradayNames,
    dayAheadEvidence: declarations.dayAheadEvidence ?? emptyEvidenceDeclaration(),
    intradayEvidence: declarations.intradayEvidence ?? emptyEvidenceDeclaration(),
    preservedEvidenceTargets: preserved,
    evidenceRedeclarationRequired: redeclarationRequired,
    weight: String(extension.weight ?? 1.0),
    positiveThreshold: String(extension.positive_spread_threshold_gbp_mwh ?? 0.0),
    negativeThreshold: String(extension.negative_spread_threshold_gbp_mwh ?? 0.0),
    windowStart: String(extension.time_window_start ?? "05:00"),
    windowEnd: String(extension.time_window_end ?? "05:30"),
    barMinutes: String(extension.target_bar_minutes ?? 5),
    maxOcm: String(risk.max_ocm_allocation_pct ?? 80.0),
    minDayAhead: String(risk.min_day_ahead_allocation_pct ?? 10.0),
    requireTsoAccess: Boolean(risk.require_tso_access),
    resourceId: String(resources?.resource_id ?? ""),
    resourceName: String(resources?.resource_name ?? ""),
    resourceQuantity: String(resources?.available_quantity_mwh_per_day ?? ""),
    resourceCost: String(resources?.all_in_cost_gbp_mwh ?? ""),
  };
}

/**
 * Read the stored declaration array, keeping unrecognized entries verbatim.
 *
 * A non-array value is an unreadable declaration rather than "no declaration":
 * the surface must not overwrite it by pretending it was absent.
 */
function readStoredEvidenceTargets(value: unknown): unknown[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) return [{ unreadable: value }];
  return value.map((entry) =>
    entry && typeof entry === "object" ? entry : { unreadable: entry },
  );
}

export function strategyCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function numberValue(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export interface StrategyDraftValidation {
  readonly blockerKeys: readonly string[];
  readonly warningKeys: readonly string[];
}

function evidenceDeclarationBlocker(
  declaration: StrategyEvidenceDeclarationState,
): string | null {
  if (!declaration.role.trim() || !STRATEGY_EVIDENCE_ROLES.includes(declaration.role)) {
    return "strategy_lab.blocker.evidence_role";
  }
  if (!declaration.hub.trim() || !declaration.tenor.trim() || !declaration.priceBasis.trim()) {
    return "strategy_lab.blocker.evidence_fields";
  }
  if (!STRATEGY_EVIDENCE_TARGET_BASES.includes(declaration.targetBasis)) {
    // Month/quarter rolls and any other basis are not implemented; a declaration
    // the engine cannot resolve must not be stored.
    return "strategy_lab.blocker.evidence_basis";
  }
  if (declaration.targetBasis === STRATEGY_GAS_DAY_BASIS) {
    if (!STRATEGY_GAS_DAY_CALENDARS.includes(declaration.calendarId)) {
      return "strategy_lab.blocker.evidence_calendar";
    }
    if (!STRATEGY_GAS_DAY_OFFSETS.includes(declaration.gasDayOffset)) {
      return "strategy_lab.blocker.evidence_offset";
    }
    return null;
  }
  // The explicit declaration is a fixed UTC interval: an unordered endpoint pair
  // cannot describe one, and a reference level's validity interval is stated
  // the same way.
  const start = utcIsoFromInput(declaration.deliveryStartUtc);
  const end = utcIsoFromInput(declaration.deliveryEndUtc);
  if (!start || !end) return "strategy_lab.blocker.evidence_interval";
  if (new Date(end).getTime() <= new Date(start).getTime()) {
    return "strategy_lab.blocker.evidence_interval_order";
  }
  return null;
}

/**
 * The declaration blocker for this draft, or `null`.
 *
 * An opted-in leg must be complete - the frozen definition is immutable, so an
 * incomplete declaration would either be refused by the backend later or, far
 * worse, be stored as something the operator did not declare. A leg left unset
 * declares nothing, which is allowed: EVALUATION does not need targets and a
 * draft with no declarations must remain saveable.
 */
export function strategyEvidenceBlocker(form: StrategyDesignFormState): string | null {
  if (form.unsupportedDefinition) return "strategy_lab.blocker.unsupported_definition";
  if (form.evidenceRedeclarationRequired) {
    return "strategy_lab.blocker.evidence_redeclare";
  }
  for (const leg of STRATEGY_EVIDENCE_LEGS) {
    const declaration = form[leg.stateKey];
    if (!declaration.enabled) continue;
    const blocker = evidenceDeclarationBlocker(declaration);
    if (blocker) return blocker;
  }
  return null;
}

/**
 * What stops this draft being written, as translation keys.
 *
 * The thresholds are the surface's own contract: a strategy without a name, without either price
 * series, or without a usable resource cannot be evaluated, and a modeled cost that does not parse
 * would change the backtest rather than the request.
 */
export function strategyDraftValidation(form: StrategyDesignFormState): StrategyDraftValidation {
  const blockerKeys: string[] = [];
  const warningKeys: string[] = [];
  if (!form.name.trim()) blockerKeys.push("strategy_lab.blocker.name");
  if (strategyCsv(form.hubs).length === 0) blockerKeys.push("strategy_lab.blocker.hubs");
  if (strategyCsv(form.dayAheadNames).length === 0) {
    blockerKeys.push("strategy_lab.blocker.day_ahead");
  }
  if (strategyCsv(form.intradayNames).length === 0) {
    blockerKeys.push("strategy_lab.blocker.intraday");
  }
  const quantity = numberValue(form.resourceQuantity);
  const cost = numberValue(form.resourceCost);
  if (!form.resourceId.trim() || !form.resourceName.trim() || form.resourceBasisBlocked ||
      quantity === null || quantity <= 0 || cost === null || cost <= 0) {
    blockerKeys.push("strategy_lab.blocker.resource");
  }
  if (form.transactionCostTreatment === "MODELED_COST" && numberValue(form.transactionCost) === null) {
    blockerKeys.push("strategy_lab.blocker.transaction_cost");
  }
  if (form.transactionCostTreatment === "UNAVAILABLE") {
    warningKeys.push("strategy_lab.warning.transaction_cost_unavailable");
  }
  if (form.missingDataPolicy === "CARRY_FORWARD_WITH_MAX_AGE") {
    warningKeys.push("strategy_lab.warning.carry_forward");
  }
  const evidenceBlocker = strategyEvidenceBlocker(form);
  if (evidenceBlocker) blockerKeys.push(evidenceBlocker);
  return { blockerKeys, warningKeys };
}

export interface StrategyDraftReadiness {
  readonly canSave: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/**
 * Whether the draft may be written, and what stops it.
 *
 * A frozen version is not editable through this act at all - its numbers can no longer move - so a
 * frozen draft is not "blocked", it is *not this act*: the surface offers forking a new version
 * instead, which the geography keeps out of the primary slot.
 */
export function strategyDraftReadiness(input: {
  readonly validation: StrategyDraftValidation;
  readonly busy: boolean;
  readonly frozen: boolean;
}): StrategyDraftReadiness {
  const blockerKeys = [...input.validation.blockerKeys];
  if (input.frozen) blockerKeys.push("strategy_lab.blocker.frozen_edit");
  if (input.busy) blockerKeys.push("strategy_lab.blocker.in_flight");
  return {
    canSave: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/** Build the typed declaration for one opted-in leg, or `null` when it is unset. */
export function evidenceTargetFromLeg(
  leg: StrategyEvidenceLegSpec,
  declaration: StrategyEvidenceDeclarationState,
  priceNames: readonly string[],
): StrategyEvidenceTargetDeclaration | null {
  if (!declaration.enabled) return null;
  if (!STRATEGY_EVIDENCE_TARGET_BASES.includes(declaration.targetBasis)) return null;
  const shared = {
    leg_id: leg.legId,
    // The leg's existing names, not a renamed copy: the declaration addresses
    // exactly the series the strategy already consumes.
    price_names: [...priceNames],
    role: declaration.role,
    hub: declaration.hub.trim(),
    tenor: declaration.tenor.trim(),
    price_basis: declaration.priceBasis.trim(),
  };
  if (declaration.targetBasis === STRATEGY_GAS_DAY_BASIS) {
    return {
      ...shared,
      target_basis: STRATEGY_GAS_DAY_BASIS,
      calendar_id: declaration.calendarId,
      gas_day_offset: declaration.gasDayOffset === "1" ? 1 : 0,
    };
  }
  const start = utcIsoFromInput(declaration.deliveryStartUtc);
  const end = utcIsoFromInput(declaration.deliveryEndUtc);
  if (!start || !end) return null;
  return {
    ...shared,
    target_basis: STRATEGY_EXPLICIT_BASIS,
    delivery_start_utc: start,
    delivery_end_utc: end,
  };
}

/**
 * Every declaration the body should carry, in leg order.
 *
 * Declarations the form cannot edit are appended verbatim, so a fork preserves
 * semantics this slice does not understand instead of discarding them.
 */
export function strategyEvidenceTargets(
  form: StrategyDesignFormState,
): StrategyEvidenceTargetDeclaration[] | null {
  const namesByLeg: Record<string, readonly string[]> = {
    day_ahead: strategyCsv(form.dayAheadNames),
    intraday: strategyCsv(form.intradayNames),
  };
  const targets: StrategyEvidenceTargetDeclaration[] = [];
  for (const leg of STRATEGY_EVIDENCE_LEGS) {
    const target = evidenceTargetFromLeg(
      leg,
      form[leg.stateKey],
      namesByLeg[leg.legId] ?? [],
    );
    if (target) targets.push(target);
  }
  return targets.length > 0 ? targets : null;
}

/**
 * The request body a draft describes.
 *
 * The body is built here because the action that sends it lives in the workspace: a panel that
 * built its own request could send something the header never approved.
 */
export function strategyDraftBody(form: StrategyDesignFormState): StrategyVersionCreateInputDTO {
  if (strategyDraftValidation(form).blockerKeys.includes("strategy_lab.blocker.resource")) {
    throw new Error("An explicit compatible resource and all-in cost are required.");
  }
  const evidenceTargets = strategyEvidenceTargets(form);
  const component = {
    component_id: "ocm-da-1",
    component_type: "OCM_VS_DAY_AHEAD",
    hubs: strategyCsv(form.hubs),
    tenors: ["within-day", "day-ahead"],
    extension_json: {
      weight: numberValue(form.weight) ?? 1.0,
      day_ahead_price_names: strategyCsv(form.dayAheadNames),
      intraday_price_names: strategyCsv(form.intradayNames),
      positive_spread_threshold_gbp_mwh: numberValue(form.positiveThreshold) ?? 0,
      negative_spread_threshold_gbp_mwh: numberValue(form.negativeThreshold) ?? 0,
      time_window_start: form.windowStart || null,
      time_window_end: form.windowEnd || null,
      target_bar_minutes: numberValue(form.barMinutes) ?? 5,
    },
  };
  // Absent means "declares nothing"; the backend omits the field entirely, so
  // an undeclared draft keeps its pre-amendment hash.
  const declared = [...(evidenceTargets ?? []), ...form.preservedEvidenceTargets];
  return {
    hypothesis: form.hypothesis,
    definition: {
      components: [
        declared.length > 0 ? { ...component, evidence_targets: declared } : component,
      ],
      parameter_definitions: [],
      parameter_values: {},
      risk_controls: {
        max_ocm_allocation_pct: numberValue(form.maxOcm) ?? 80,
        min_day_ahead_allocation_pct: numberValue(form.minDayAhead) ?? 10,
        require_tso_access: form.requireTsoAccess,
      },
      economic_assumptions: {
        fill_price_policy: form.fillPricePolicy,
        missing_data_policy: form.missingDataPolicy,
        cost_components: [
          {
            code: "TRANSACTION_COST",
            treatment: form.transactionCostTreatment,
            amount_gbp_mwh:
              form.transactionCostTreatment === "MODELED_COST"
                ? numberValue(form.transactionCost)
                : null,
          },
          {
            code: "SLIPPAGE",
            treatment: form.slippageTreatment,
            amount_gbp_mwh:
              form.slippageTreatment === "MODELED_COST" ? numberValue(form.slippage) : null,
          },
        ],
      },
      data_requirements: { hubs: strategyCsv(form.hubs) },
      evaluation_windows: [],
    },
    strategy_name: form.name,
    run_mode: "BACKTEST",
    resource_contexts: [
      {
        resource_id: form.resourceId,
        resource_name: form.resourceName,
        available_quantity_mwh_per_day: numberValue(form.resourceQuantity)!,
        all_in_cost_gbp_mwh: numberValue(form.resourceCost)!,
        required_tso_access: [],
      },
    ],
    price_observations: [],
    existing_shadow_pnl_gbp: 0,
  };
}

/** The name a first save uses when the operator has not typed one. */
export function strategyDraftName(form: StrategyDesignFormState): string {
  return form.name.trim() || "Untitled strategy";
}

/** Whether the selected version may be edited in place. */
export function strategyVersionEditable(version: StrategyVersionDTO | null): boolean {
  return version?.status === "DRAFT";
}

/** Whether the selected version is frozen, i.e. its numbers can no longer move. */
export function strategyVersionFrozen(version: StrategyVersionDTO | null): boolean {
  return version?.status === "FROZEN";
}
