/**
 * Display-only context for one native flow observation against one native technical capacity.
 *
 * The backend owns the quantities, their dimensions and their normalised units. This module
 * performs a transport-shape check and a ratio for the label only; it never converts, scales,
 * aggregates, nets, reserves or rights-checks a quantity. The exact canonical rate strings are
 * carried through untouched, while `indicativeRatioPct` is approximate display context under
 * RFC 0005 and must never become economic evidence or a risk/headroom calculation.
 *
 * A null ratio always carries a stable `reasonCode`, so a component can say why no indication
 * was made instead of showing a fabricated comparison. No current time, default date, staleness
 * assessment or fallback to a different operator/period is introduced here.
 */

import type { NativeCapacityObsDTO, NativeFlowObsDTO } from "@/api/client";

/** Hard input bound: callers must narrow their reads instead of receiving a silent truncation. */
export const NATIVE_CAPACITY_MAX_OBSERVATIONS = 2_000;

/** The only canonical units this model can display, exactly as the v1 labels state them. */
export const NATIVE_CAPACITY_UNITS = ["kWh/day", "mcm/day"] as const;
export type NativeCapacityUnit = (typeof NATIVE_CAPACITY_UNITS)[number];

/** The frozen native-rate source/version labels the projection is allowed to compare. */
export const NATIVE_CAPACITY_SOURCE_SYSTEM = "ENTSOG";
export const NATIVE_CAPACITY_QUANTITY_BASIS = "native";
export const NATIVE_CAPACITY_NORMALIZER_VERSION = "entsog-native-units-v1";

/**
 * The exact native unit/basis pairs the backend normalizer emits per dimension.
 *
 * These are transport-validation labels only. The paired canonical daily field is already
 * scaled by the backend and is used as-is; this client performs no unit conversion.
 */
const NATIVE_RATE_SHAPES: Record<
  "energy" | "volume",
  readonly { readonly unit: string; readonly basis: string }[]
> = {
  energy: [
    { unit: "kWh/day", basis: "day" },
    { unit: "MWh/day", basis: "day" },
    { unit: "kWh/hour", basis: "hour" },
    { unit: "MWh/hour", basis: "hour" },
  ],
  volume: [
    { unit: "m3/day", basis: "day" },
    { unit: "m3/hour", basis: "hour" },
    { unit: "mcm/day", basis: "day" },
    { unit: "mcm/hour", basis: "hour" },
  ],
};

/**
 * Stable diagnostics for a missing indicated comparison.
 *
 * These are display/diagnostic codes, not backend enums or economic classifications. A component
 * owns their labels; this module only decides which one applies.
 */
export const NATIVE_CAPACITY_REASON_CODES = [
  "indicated",
  "invalid_flow_period",
  "flow_source_not_entsog_v1",
  "missing_flow_metadata",
  "flow_not_actual",
  "missing_flow_identity",
  "flow_quantity_missing",
  "flow_quantity_invalid",
  "flow_dimension_unsupported",
  "flow_unit_basis_unsupported",
  "missing_flow_lineage",
  "missing_flow_receipt",
  "negative_flow",
  "no_capacity_match",
  "capacity_source_not_entsog_v1",
  "missing_capacity_metadata",
  "capacity_not_firm_technical",
  "capacity_dimension_mismatch",
  "invalid_capacity_period",
  "capacity_period_not_covering",
  "ambiguous_capacity_match",
  "capacity_quantity_missing",
  "capacity_quantity_invalid",
  "capacity_dimension_unsupported",
  "capacity_unit_basis_unsupported",
  "missing_capacity_lineage",
  "missing_capacity_receipt",
  "capacity_not_positive",
  "ratio_not_finite",
] as const;
export type NativeCapacityReasonCode = (typeof NATIVE_CAPACITY_REASON_CODES)[number];

/**
 * One flow with its original observation references, exact displayed rates and, only when the
 * evidence is eligible, an approximate flow/capacity percentage.
 *
 * `flow` and `capacity` are the input objects themselves. `capacity` is null when no single
 * capacity passed the identity, source, type, dimension and period checks. The rate texts remain
 * the backend's exact canonical strings and can be displayed even when no comparison is indicated.
 */
export interface NativeCapacityContext {
  readonly flow: NativeFlowObsDTO;
  readonly capacity: NativeCapacityObsDTO | null;
  readonly flowRateText: string | null;
  readonly capacityRateText: string | null;
  readonly unit: NativeCapacityUnit | null;
  readonly indicativeRatioPct: number | null;
  readonly reasonCode: NativeCapacityReasonCode;
}

interface Period {
  readonly startMs: number;
  readonly endMs: number;
  readonly startText: string;
  readonly endText: string;
}

type QuantityProblem =
  | "missing"
  | "invalid"
  | "dimension"
  | "unit_basis"
  | null;

interface Quantity {
  /** Exact canonical backend decimal for the selected dimension, never re-spelled. */
  readonly valueText: string | null;
  /** Approximate binary value used only for the display percentage. */
  readonly value: number | null;
  /** Normalised energy/volume dimension, when the backend supplied a supported one. */
  readonly dimension: string | null;
  readonly canonicalUnit: NativeCapacityUnit | null;
  readonly problem: QuantityProblem;
}

interface Provenance {
  readonly lineageHash: string | null;
  readonly archiveId: string | null;
  readonly observedAtMs: number | null;
  readonly receivedAtMs: number | null;
}

type SourceCheck =
  | { readonly state: "ok" }
  | { readonly state: "missing_metadata" }
  | { readonly state: "not_entsog_v1" };

interface PreparedFlow {
  readonly raw: NativeFlowObsDTO;
  readonly record: Record<string, unknown>;
  readonly period: Period | null;
  readonly id: string;
}

interface PreparedCapacity {
  readonly raw: NativeCapacityObsDTO;
  readonly record: Record<string, unknown>;
  readonly identityKey: string | null;
  readonly source: SourceCheck;
  readonly capacityType: string | null;
  readonly dimension: string | null;
  readonly period: Period | null;
  readonly quantity: Quantity;
  readonly provenance: Provenance;
}

const UTC_ISO_PERIOD =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(?:Z|z|[+-]00:00)$/;

const DECIMAL_TEXT = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const SHA256_HEX = /^[0-9a-f]{64}$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function recordOf(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

/** An explicit, non-blank string; the original spelling is preserved for the caller. */
function textField(
  record: Record<string, unknown> | null,
  keys: readonly string[],
): string | null {
  if (!record) return null;
  for (const key of keys) {
    if (!hasOwn(record, key)) continue;
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) return value;
  }
  return null;
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  }
  return [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 0;
}

/**
 * Parse an explicit UTC ISO-8601 instant, refusing a naive timestamp or an impossible calendar
 * value. Offsets other than UTC are refused: the period is part of the evidence and is not
 * silently shifted into another zone.
 */
function parseUtcInstant(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const match = UTC_ISO_PERIOD.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = match[6] === undefined ? 0 : Number(match[6]);
  if (year < 100 || month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)) {
    return null;
  }
  if (hour > 23 || minute > 59 || second > 59) return null;
  const fraction = match[7] ?? "";
  const millisecond = Number(fraction.padEnd(3, "0").slice(0, 3) || "0");
  const parsed = Date.UTC(year, month - 1, day, hour, minute, second, millisecond);
  return Number.isFinite(parsed) ? parsed : null;
}

function periodOf(record: Record<string, unknown>): Period | null {
  const startText = textField(record, ["period_start_utc"]);
  const endText = textField(record, ["period_end_utc"]);
  if (!startText || !endText) return null;
  const startMs = parseUtcInstant(startText);
  const endMs = parseUtcInstant(endText);
  if (startMs === null || endMs === null || endMs <= startMs) return null;
  return { startMs, endMs, startText, endText };
}

function normaliseDimension(value: string | null): string | null {
  if (!value) return null;
  const dimension = value.trim().toLowerCase();
  return dimension.length > 0 ? dimension : null;
}

/**
 * Read the canonical quantity from `native_rate_json`.
 *
 * Only the backend's canonical field for the declared dimension is used. `value_text` is the
 * provider's native token and is deliberately not substituted when the dimension is volume:
 * rendering it beside `mcm/day` would be an implicit conversion this client must not perform.
 */
function quantityOf(record: Record<string, unknown>): Quantity {
  const rate = recordOf(record.native_rate_json);
  if (!rate) {
    return {
      valueText: null,
      value: null,
      dimension: null,
      canonicalUnit: null,
      problem: "missing",
    };
  }

  const dimension = normaliseDimension(textField(rate, ["quantity_kind"]));
  if (!dimension || (dimension !== "energy" && dimension !== "volume")) {
    return {
      valueText: null,
      value: null,
      dimension,
      canonicalUnit: null,
      problem: "dimension",
    };
  }

  // The backend emits exactly one canonical field for the declared dimension. A populated
  // opposite-dimension field means this is not the reviewed native-rate wire shape.
  const oppositeText =
    dimension === "energy"
      ? rate.volume_mcm_per_day
      : rate.energy_kwh_per_day;
  if (oppositeText !== null && oppositeText !== undefined) {
    return {
      valueText: null,
      value: null,
      dimension,
      canonicalUnit: null,
      problem: "dimension",
    };
  }

  const canonicalText =
    dimension === "energy"
      ? textField(rate, ["energy_kwh_per_day"])
      : textField(rate, ["volume_mcm_per_day"]);
  if (!canonicalText) {
    return {
      valueText: null,
      value: null,
      dimension,
      canonicalUnit: null,
      problem: "missing",
    };
  }

  const normalizedUnit = textField(rate, ["normalized_unit"]);
  const rateBasis = textField(rate, ["rate_basis"]);
  const expectedUnit: NativeCapacityUnit =
    dimension === "energy" ? "kWh/day" : "mcm/day";
  const acceptedShapes = NATIVE_RATE_SHAPES[dimension];
  const unitBasisSupported =
    normalizedUnit !== null &&
    rateBasis !== null &&
    acceptedShapes.some(
      (shape) => shape.unit === normalizedUnit && shape.basis === rateBasis,
    );
  if (!unitBasisSupported) {
    return {
      valueText: canonicalText,
      value: null,
      dimension,
      canonicalUnit: null,
      problem: "unit_basis",
    };
  }
  if (!DECIMAL_TEXT.test(canonicalText)) {
    return {
      valueText: canonicalText,
      value: null,
      dimension,
      canonicalUnit: expectedUnit,
      problem: "invalid",
    };
  }
  const value = Number(canonicalText);
  if (!Number.isFinite(value)) {
    return {
      valueText: canonicalText,
      value: null,
      dimension,
      canonicalUnit: expectedUnit,
      problem: "invalid",
    };
  }
  return {
    valueText: canonicalText,
    value,
    dimension,
    canonicalUnit: expectedUnit,
    problem: null,
  };
}

/**
 * Both the outer observation and the nested native-rate payload must name the frozen ENTSOG
 * source/basis/normalizer v1 labels. This is the transport-side source/version contract the
 * backend projector emits; no row metadata, source name or inferred date substitutes for it.
 */
function sourceCheck(record: Record<string, unknown>): SourceCheck {
  const sourceSystem = textField(record, ["source_system"]);
  const quantityBasis = textField(record, ["quantity_basis"]);
  const outerVersion = textField(record, ["normalizer_version"]);
  const nestedVersion = textField(recordOf(record.native_rate_json), [
    "normalizer_version",
  ]);
  if (!sourceSystem || !quantityBasis || !outerVersion || !nestedVersion) {
    return { state: "missing_metadata" };
  }
  if (
    sourceSystem !== NATIVE_CAPACITY_SOURCE_SYSTEM ||
    quantityBasis !== NATIVE_CAPACITY_QUANTITY_BASIS ||
    outerVersion !== NATIVE_CAPACITY_NORMALIZER_VERSION ||
    nestedVersion !== NATIVE_CAPACITY_NORMALIZER_VERSION
  ) {
    return { state: "not_entsog_v1" };
  }
  return { state: "ok" };
}

function identityOf(
  record: Record<string, unknown>,
): { readonly operator: string; readonly point: string; readonly direction: string } | null {
  const operator = textField(record, ["operator_key"]);
  const point = textField(record, ["point_id"]);
  const direction = textField(record, ["direction"]);
  if (!operator || !point || !direction) return null;
  return {
    operator: operator.trim(),
    point: point.trim(),
    direction: direction.trim().toLowerCase(),
  };
}

function identityKeyOf(
  operator: string,
  point: string,
  direction: string,
): string {
  return `${operator}\u0000${point}\u0000${direction}`;
}

function provenanceOf(record: Record<string, unknown>): Provenance {
  const rawHash = textField(record, ["payload_sha256"]);
  const lineageHash = rawHash && SHA256_HEX.test(rawHash) ? rawHash : null;
  return {
    lineageHash,
    archiveId: textField(record, ["raw_archive_id"]),
    observedAtMs: parseUtcInstant(record.observed_at_utc),
    receivedAtMs: parseUtcInstant(record.received_at_utc),
  };
}

function comparePreparedFlows(left: PreparedFlow, right: PreparedFlow): number {
  const leftStart = left.period?.startMs ?? Number.POSITIVE_INFINITY;
  const rightStart = right.period?.startMs ?? Number.POSITIVE_INFINITY;
  if (leftStart !== rightStart) return leftStart - rightStart;
  const leftEnd = left.period?.endMs ?? Number.POSITIVE_INFINITY;
  const rightEnd = right.period?.endMs ?? Number.POSITIVE_INFINITY;
  if (leftEnd !== rightEnd) return leftEnd - rightEnd;
  return left.id.localeCompare(right.id);
}

/**
 * Build one context per flow, in stable flow-period/id order.
 *
 * Matching is indexed by operator/point/direction before any flow is inspected, and every
 * capacity period and quantity is parsed once. A capacity must be the same ENTSOG v1 source,
 * `firm_technical`, the same dimension, and cover the whole flow period. More than one covering
 * candidate is reported as ambiguous rather than choosing a "latest" row.
 */
export function buildNativeCapacityContext(
  flows: readonly NativeFlowObsDTO[],
  capacities: readonly NativeCapacityObsDTO[],
): NativeCapacityContext[] {
  if (!Array.isArray(flows) || !Array.isArray(capacities)) {
    throw new TypeError("Native flow and capacity observation arrays are required.");
  }
  if (
    flows.length > NATIVE_CAPACITY_MAX_OBSERVATIONS ||
    capacities.length > NATIVE_CAPACITY_MAX_OBSERVATIONS
  ) {
    throw new RangeError(
      `At most ${NATIVE_CAPACITY_MAX_OBSERVATIONS} native flows and capacities may be processed.`,
    );
  }

  const preparedFlows: PreparedFlow[] = flows.map((flow) => {
    const record = (isRecord(flow) ? flow : {}) as Record<string, unknown>;
    return {
      raw: flow,
      record,
      period: periodOf(record),
      id: textField(record, ["observation_id"]) ?? "",
    };
  });

  const preparedCapacities: PreparedCapacity[] = capacities.map((capacity) => {
    const record = (isRecord(capacity) ? capacity : {}) as Record<string, unknown>;
    const identity = identityOf(record);
    const quantity = quantityOf(record);
    return {
      raw: capacity,
      record,
      identityKey: identity
        ? identityKeyOf(identity.operator, identity.point, identity.direction)
        : null,
      source: sourceCheck(record),
      capacityType: textField(record, ["capacity_type"]),
      dimension: quantity.dimension,
      period: periodOf(record),
      quantity,
      provenance: provenanceOf(record),
    };
  });

  const capacityIndex = new Map<string, PreparedCapacity[]>();
  for (const capacity of preparedCapacities) {
    if (!capacity.identityKey) continue;
    const bucket = capacityIndex.get(capacity.identityKey);
    if (bucket) bucket.push(capacity);
    else capacityIndex.set(capacity.identityKey, [capacity]);
  }

  const orderedFlows = [...preparedFlows].sort(comparePreparedFlows);
  const contexts: NativeCapacityContext[] = [];

  for (const prepared of orderedFlows) {
    const { record } = prepared;
    const quantity = quantityOf(record);
    const source = sourceCheck(record);
    const identity = identityOf(record);
    const kind = textField(record, ["kind"]);
    const provenance = provenanceOf(record);
    const flowUnit = quantity.canonicalUnit;

    const result = (
      reasonCode: NativeCapacityReasonCode,
      capacity: NativeCapacityObsDTO | null = null,
      capacityQuantity: Quantity | null = null,
      ratio: number | null = null,
    ): NativeCapacityContext => ({
      flow: prepared.raw,
      capacity,
      flowRateText: quantity.valueText,
      capacityRateText: capacityQuantity?.valueText ?? null,
      unit: flowUnit,
      indicativeRatioPct: ratio,
      reasonCode,
    });

    if (!prepared.period) {
      contexts.push(result("invalid_flow_period"));
      continue;
    }
    const flowPeriod = prepared.period;
    if (source.state === "missing_metadata") {
      contexts.push(result("missing_flow_metadata"));
      continue;
    }
    if (source.state === "not_entsog_v1") {
      contexts.push(result("flow_source_not_entsog_v1"));
      continue;
    }
    if (kind !== "actual") {
      contexts.push(result("flow_not_actual"));
      continue;
    }
    if (!identity) {
      contexts.push(result("missing_flow_identity"));
      continue;
    }
    if (quantity.problem === "missing") {
      contexts.push(result("flow_quantity_missing"));
      continue;
    }
    if (quantity.problem === "dimension") {
      contexts.push(result("flow_dimension_unsupported"));
      continue;
    }
    if (quantity.problem === "unit_basis") {
      contexts.push(result("flow_unit_basis_unsupported"));
      continue;
    }
    if (quantity.problem === "invalid" || quantity.value === null || !quantity.dimension) {
      contexts.push(result("flow_quantity_invalid"));
      continue;
    }
    if (!provenance.lineageHash || !provenance.archiveId) {
      contexts.push(result("missing_flow_lineage"));
      continue;
    }
    if (provenance.observedAtMs === null || provenance.receivedAtMs === null) {
      contexts.push(result("missing_flow_receipt"));
      continue;
    }
    if (quantity.value < 0) {
      contexts.push(result("negative_flow"));
      continue;
    }

    const candidates =
      capacityIndex.get(
        identityKeyOf(identity.operator, identity.point, identity.direction),
      ) ?? [];
    if (candidates.length === 0) {
      contexts.push(result("no_capacity_match"));
      continue;
    }

    const sourceEligible = candidates.filter((candidate) => candidate.source.state === "ok");
    if (sourceEligible.length === 0) {
      const missingMetadata = candidates.some(
        (candidate) => candidate.source.state === "missing_metadata",
      );
      contexts.push(
        result(
          missingMetadata
            ? "missing_capacity_metadata"
            : "capacity_source_not_entsog_v1",
        ),
      );
      continue;
    }

    const typeEligible = sourceEligible.filter(
      (candidate) => candidate.capacityType === "firm_technical",
    );
    if (typeEligible.length === 0) {
      contexts.push(result("capacity_not_firm_technical"));
      continue;
    }

    const sameDimension = typeEligible.filter(
      (candidate) => candidate.dimension === quantity.dimension,
    );
    if (sameDimension.length === 0) {
      contexts.push(result("capacity_dimension_mismatch"));
      continue;
    }

    if (sameDimension.every((candidate) => candidate.period === null)) {
      contexts.push(result("invalid_capacity_period"));
      continue;
    }

    const covering = sameDimension.filter(
      (candidate) =>
        candidate.period !== null &&
        candidate.period.startMs <= flowPeriod.startMs &&
        candidate.period.endMs >= flowPeriod.endMs,
    );
    if (covering.length === 0) {
      contexts.push(result("capacity_period_not_covering"));
      continue;
    }
    if (covering.length > 1) {
      contexts.push(result("ambiguous_capacity_match"));
      continue;
    }

    const capacity = covering[0];
    if (!capacity) {
      contexts.push(result("no_capacity_match"));
      continue;
    }
    if (capacity.quantity.problem === "missing") {
      contexts.push(result("capacity_quantity_missing", capacity.raw));
      continue;
    }
    if (capacity.quantity.problem === "dimension") {
      contexts.push(result("capacity_dimension_unsupported", capacity.raw, capacity.quantity));
      continue;
    }
    if (capacity.quantity.problem === "unit_basis") {
      contexts.push(result("capacity_unit_basis_unsupported", capacity.raw, capacity.quantity));
      continue;
    }
    if (
      capacity.quantity.problem === "invalid" ||
      capacity.quantity.value === null ||
      !capacity.quantity.dimension
    ) {
      contexts.push(result("capacity_quantity_invalid", capacity.raw, capacity.quantity));
      continue;
    }
    if (!capacity.provenance.lineageHash || !capacity.provenance.archiveId) {
      contexts.push(result("missing_capacity_lineage", capacity.raw, capacity.quantity));
      continue;
    }
    if (
      capacity.provenance.observedAtMs === null ||
      capacity.provenance.receivedAtMs === null
    ) {
      contexts.push(result("missing_capacity_receipt", capacity.raw, capacity.quantity));
      continue;
    }
    if (capacity.quantity.value <= 0) {
      contexts.push(result("capacity_not_positive", capacity.raw, capacity.quantity));
      continue;
    }

    const ratio = (quantity.value / capacity.quantity.value) * 100;
    if (!Number.isFinite(ratio)) {
      contexts.push(result("ratio_not_finite", capacity.raw, capacity.quantity));
      continue;
    }
    contexts.push(
      result("indicated", capacity.raw, capacity.quantity, ratio === 0 ? 0 : ratio),
    );
  }

  return contexts;
}
