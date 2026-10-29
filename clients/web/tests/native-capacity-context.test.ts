/**
 * Native flow/capacity display context.
 *
 * These fixtures are the backend `entsog-native-units-v1` wire shape: flat ENTSOG/source and
 * normalizer labels, `native_rate_json` with the exact canonical decimal, `payload_sha256` plus
 * `raw_archive_id` lineage, and aware observed/received instants. The tests pin the boundaries
 * that matter for the label: exact canonical strings survive, only one covering firm-technical
 * candidate may produce a percentage, and a missing indication is always explicit rather than a
 * zero, a fallback or a converted quantity.
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  NATIVE_CAPACITY_MAX_OBSERVATIONS,
  NATIVE_CAPACITY_NORMALIZER_VERSION,
  buildNativeCapacityContext,
} from "../src/app/model/nativeCapacityContext.ts";

const FLOW_START = "2026-10-28T00:00:00+00:00";
const FLOW_END = "2026-10-29T00:00:00+00:00";
const TWO_DAY_CAPACITY_START = "2026-10-27T00:00:00+00:00";
const TWO_DAY_CAPACITY_END = "2026-10-29T00:00:00+00:00";
const RECEIVED_AT = "2026-10-28T01:02:03+00:00";
const PAYLOAD_SHA256 = "a".repeat(64);
const CAPACITY_SHA256 = "b".repeat(64);

function rate(
  canonicalValue: string,
  kind: "energy" | "volume" = "energy",
  sourceValue = canonicalValue,
  overrides: Record<string, unknown> = {},
) {
  const energy = kind === "energy";
  return {
    value_text: sourceValue,
    unit_text: energy ? "kWh/d" : "m3/d",
    native_value: sourceValue,
    normalized_unit: energy ? "kWh/day" : "m3/day",
    quantity_kind: kind,
    rate_basis: "day",
    energy_kwh_per_day: energy ? canonicalValue : null,
    volume_mcm_per_day: energy ? null : canonicalValue,
    normalizer_version: NATIVE_CAPACITY_NORMALIZER_VERSION,
    ...overrides,
  };
}

function flow(overrides: Record<string, unknown> = {}) {
  return {
    observation_id: "entsog-flow-n1-1",
    source_record_id: "provider-flow-1",
    point_id: "ITP-00126",
    point_name: "Punto di scambio",
    direction: "entry",
    kind: "actual",
    period_start_utc: FLOW_START,
    period_end_utc: FLOW_END,
    observed_at_utc: RECEIVED_AT,
    source_system: "ENTSOG",
    operator_key: "DE-TSO-0009",
    flow_status: null,
    period_type: "day",
    source_reference: "entsog-operationaldatas;offset=0;limit=100",
    research_only: true,
    quantity_basis: "native",
    normalizer_version: NATIVE_CAPACITY_NORMALIZER_VERSION,
    native_rate_json: rate("92954921"),
    raw_archive_id: "raw-0123456789abcdef0123",
    payload_sha256: PAYLOAD_SHA256,
    received_at_utc: RECEIVED_AT,
    ...overrides,
  };
}

function capacity(overrides: Record<string, unknown> = {}) {
  return {
    observation_id: "entsog-capacity-n1-1",
    source_record_id: "provider-capacity-1",
    point_id: "ITP-00126",
    point_name: "Punto di scambio",
    direction: "entry",
    capacity_type: "firm_technical",
    period_start_utc: TWO_DAY_CAPACITY_START,
    period_end_utc: TWO_DAY_CAPACITY_END,
    observed_at_utc: RECEIVED_AT,
    source_system: "ENTSOG",
    operator_key: "DE-TSO-0009",
    flow_status: null,
    period_type: "day",
    source_reference: "entsog-operationaldatas;offset=0;limit=100",
    research_only: true,
    quantity_basis: "native",
    normalizer_version: NATIVE_CAPACITY_NORMALIZER_VERSION,
    native_rate_json: rate("416592000"),
    raw_archive_id: "raw-89abcdef0123456789ab",
    payload_sha256: CAPACITY_SHA256,
    received_at_utc: RECEIVED_AT,
    ...overrides,
  };
}

function build(
  flowOverrides: Record<string, unknown> = {},
  capacityOverrides: Record<string, unknown> | null = {},
) {
  const flows = [flow(flowOverrides)];
  const capacities = capacityOverrides === null ? [] : [capacity(capacityOverrides)];
  return buildNativeCapacityContext(flows as never, capacities as never)[0]!;
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

test("real ENTSOG samples produce approximate, unclipped display percentages", () => {
  const first = build();
  assert.equal(first.reasonCode, "indicated");
  assert.equal(first.flowRateText, "92954921");
  assert.equal(first.capacityRateText, "416592000");
  assert.equal(first.unit, "kWh/day");
  assert.ok(first.indicativeRatioPct !== null);
  assert.ok(Math.abs(first.indicativeRatioPct - 22.3131795) < 0.00001);

  const second = build({
    native_rate_json: rate("738726002.1"),
  });
  assert.equal(second.reasonCode, "indicated");
  assert.ok(second.indicativeRatioPct !== null);
  assert.ok(second.indicativeRatioPct > 100);
  assert.ok(Math.abs(second.indicativeRatioPct - 177.3260173) < 0.000001);
});

test("exact canonical long strings are retained and never rewritten", () => {
  const longFlow = "92954921.123456789012345678901234567890";
  const longCapacity = "416592000.000000000000000000000000000001";
  const context = build(
    { native_rate_json: rate(longFlow) },
    { native_rate_json: rate(longCapacity) },
  );
  assert.equal(context.reasonCode, "indicated");
  assert.equal(context.flowRateText, longFlow);
  assert.equal(context.capacityRateText, longCapacity);
  assert.equal(context.unit, "kWh/day");
  assert.ok(context.indicativeRatioPct !== null);
  assert.ok(Number.isFinite(context.indicativeRatioPct));
});

test("a two-day static capacity covers a one-day flow period", () => {
  const context = build();
  assert.equal(context.reasonCode, "indicated");
  assert.equal(context.capacity?.observation_id, "entsog-capacity-n1-1");
});

test("partial overlap or a period starting after the flow is insufficient", () => {
  const endsInside = build(
    {},
    { period_end_utc: "2026-10-29T00:00:01+00:00" && "2026-10-28T23:59:59+00:00" },
  );
  assert.equal(endsInside.indicativeRatioPct, null);
  assert.equal(endsInside.reasonCode, "capacity_period_not_covering");
  assert.equal(endsInside.capacity, null);

  const startsInside = build(
    {},
    { period_start_utc: "2026-10-28T00:00:01+00:00" },
  );
  assert.equal(startsInside.indicativeRatioPct, null);
  assert.equal(startsInside.reasonCode, "capacity_period_not_covering");
});

test("more than one covering candidate is ambiguous, not a latest-row choice", () => {
  const flows = [flow()];
  const capacities = [
    capacity(),
    capacity({
      observation_id: "entsog-capacity-n1-2",
      payload_sha256: "c".repeat(64),
      raw_archive_id: "raw-cccccccccccccccccccc",
    }),
  ];
  const contexts = buildNativeCapacityContext(flows as never, capacities as never);
  assert.equal(contexts[0]?.indicativeRatioPct, null);
  assert.equal(contexts[0]?.reasonCode, "ambiguous_capacity_match");
  assert.equal(contexts[0]?.capacity, null);
});

test("another operator never falls back to a different capacity row", () => {
  const context = build({}, { operator_key: "OTHER-TSO" });
  assert.equal(context.reasonCode, "no_capacity_match");
  assert.equal(context.indicativeRatioPct, null);
  assert.equal(context.capacity, null);
});

test("native hourly and MWh labels are accepted; canonical daily fields stay untouched", () => {
  const hourly = build({
    native_rate_json: rate("240", "energy", "10", {
      unit_text: "kWh/h",
      normalized_unit: "kWh/hour",
      rate_basis: "hour",
    }),
  });
  assert.equal(hourly.reasonCode, "indicated");
  assert.equal(hourly.unit, "kWh/day");
  assert.equal(hourly.flowRateText, "240");
  assert.equal(hourly.indicativeRatioPct, (240 / 416592000) * 100);

  const mwhCapacity = build(
    {},
    {
      native_rate_json: rate("416592000", "energy", "416592", {
        unit_text: "MWh/d",
        normalized_unit: "MWh/day",
      }),
    },
  );
  assert.equal(mwhCapacity.reasonCode, "indicated");
  assert.equal(mwhCapacity.unit, "kWh/day");
  assert.equal(mwhCapacity.capacityRateText, "416592000");
  assert.equal(mwhCapacity.indicativeRatioPct, (92954921 / 416592000) * 100);
});

test("unknown dimensions, mismatched unit/basis and opposite canonical fields are refused", () => {
  const missingDimension = build({
    native_rate_json: rate("10", "energy", "10", { quantity_kind: "other" }),
  });
  assert.equal(missingDimension.reasonCode, "flow_dimension_unsupported");
  assert.equal(missingDimension.indicativeRatioPct, null);

  const wrongBasis = build({
    native_rate_json: rate("10", "energy", "10", {
      unit_text: "kWh/d",
      normalized_unit: "kWh/day",
      rate_basis: "hour",
    }),
  });
  assert.equal(wrongBasis.reasonCode, "flow_unit_basis_unsupported");
  assert.equal(wrongBasis.flowRateText, "10");
  assert.equal(wrongBasis.indicativeRatioPct, null);

  const wrongDimensionUnit = build({
    native_rate_json: rate("10", "energy", "10", {
      unit_text: "m3/d",
      normalized_unit: "m3/day",
      rate_basis: "day",
    }),
  });
  assert.equal(wrongDimensionUnit.reasonCode, "flow_unit_basis_unsupported");
  assert.equal(wrongDimensionUnit.indicativeRatioPct, null);

  const oppositeEnergyField = build({
    native_rate_json: rate("10", "energy", "10", { volume_mcm_per_day: "0.001" }),
  });
  assert.equal(oppositeEnergyField.reasonCode, "flow_dimension_unsupported");
  assert.equal(oppositeEnergyField.indicativeRatioPct, null);

  const wrongCapacityBasis = build(
    {},
    {
      native_rate_json: rate("100", "energy", "100", {
        unit_text: "MWh/d",
        normalized_unit: "MWh/day",
        rate_basis: "hour",
      }),
    },
  );
  assert.equal(wrongCapacityBasis.reasonCode, "capacity_unit_basis_unsupported");
  assert.equal(wrongCapacityBasis.capacityRateText, "100");
  assert.equal(wrongCapacityBasis.indicativeRatioPct, null);

  const oppositeCapacityField = build(
    { native_rate_json: rate("0.25", "volume", "250000") },
    {
      native_rate_json: rate("1", "volume", "1000000", {
        energy_kwh_per_day: "100",
      }),
    },
  );
  assert.equal(oppositeCapacityField.reasonCode, "capacity_dimension_unsupported");
  assert.equal(oppositeCapacityField.indicativeRatioPct, null);
});

test("every reviewed native unit/dimension/basis combination is accepted", () => {
  const reviewedRates = [
    {
      name: "energy kWh/day",
      kind: "energy",
      unitText: "kWh/d",
      normalizedUnit: "kWh/day",
      basis: "day",
      flowNative: "10",
      flowCanonical: "10",
      capacityNative: "100",
      capacityCanonical: "100",
    },
    {
      name: "energy MWh/day",
      kind: "energy",
      unitText: "MWh/d",
      normalizedUnit: "MWh/day",
      basis: "day",
      flowNative: "0.01",
      flowCanonical: "10",
      capacityNative: "0.1",
      capacityCanonical: "100",
    },
    {
      name: "energy kWh/hour",
      kind: "energy",
      unitText: "kWh/h",
      normalizedUnit: "kWh/hour",
      basis: "hour",
      flowNative: "0.5",
      flowCanonical: "12",
      capacityNative: "5",
      capacityCanonical: "120",
    },
    {
      name: "energy MWh/hour",
      kind: "energy",
      unitText: "MWh/h",
      normalizedUnit: "MWh/hour",
      basis: "hour",
      flowNative: "0.0005",
      flowCanonical: "12",
      capacityNative: "0.005",
      capacityCanonical: "120",
    },
    {
      name: "volume m3/day",
      kind: "volume",
      unitText: "m3/d",
      normalizedUnit: "m3/day",
      basis: "day",
      flowNative: "10",
      flowCanonical: "0.00001",
      capacityNative: "100",
      capacityCanonical: "0.0001",
    },
    {
      name: "volume m3/hour",
      kind: "volume",
      unitText: "m3/h",
      normalizedUnit: "m3/hour",
      basis: "hour",
      flowNative: "10",
      flowCanonical: "0.00024",
      capacityNative: "100",
      capacityCanonical: "0.0024",
    },
    {
      name: "volume mcm/day",
      kind: "volume",
      unitText: "mcm/d",
      normalizedUnit: "mcm/day",
      basis: "day",
      flowNative: "0.00001",
      flowCanonical: "0.00001",
      capacityNative: "0.0001",
      capacityCanonical: "0.0001",
    },
    {
      name: "volume mcm/hour",
      kind: "volume",
      unitText: "mcm/h",
      normalizedUnit: "mcm/hour",
      basis: "hour",
      flowNative: "0.00001",
      flowCanonical: "0.00024",
      capacityNative: "0.0001",
      capacityCanonical: "0.0024",
    },
  ] as const;

  for (const reviewed of reviewedRates) {
    const context = build(
      {
        native_rate_json: rate(reviewed.flowCanonical, reviewed.kind, reviewed.flowNative, {
          unit_text: reviewed.unitText,
          normalized_unit: reviewed.normalizedUnit,
          rate_basis: reviewed.basis,
        }),
      },
      {
        native_rate_json: rate(
          reviewed.capacityCanonical,
          reviewed.kind,
          reviewed.capacityNative,
          {
            unit_text: reviewed.unitText,
            normalized_unit: reviewed.normalizedUnit,
            rate_basis: reviewed.basis,
          },
        ),
      },
    );
    assert.equal(context.reasonCode, "indicated", reviewed.name);
    assert.equal(
      context.unit,
      reviewed.kind === "energy" ? "kWh/day" : "mcm/day",
      reviewed.name,
    );
    assert.equal(context.flowRateText, reviewed.flowCanonical, reviewed.name);
    assert.equal(context.capacityRateText, reviewed.capacityCanonical, reviewed.name);
    assert.ok(context.indicativeRatioPct !== null, reviewed.name);
    assert.ok(
      Math.abs(context.indicativeRatioPct - 10) < 1e-9,
      reviewed.name,
    );
  }
});

test("mixed native units compare canonical daily fields, never the native token", () => {
  const energy = build(
    {
      native_rate_json: rate("12", "energy", "0.5", {
        unit_text: "kWh/h",
        normalized_unit: "kWh/hour",
        rate_basis: "hour",
      }),
    },
    {
      native_rate_json: rate("12", "energy", "0.012", {
        unit_text: "MWh/d",
        normalized_unit: "MWh/day",
        rate_basis: "day",
      }),
    },
  );
  assert.equal(energy.reasonCode, "indicated");
  assert.equal(energy.unit, "kWh/day");
  assert.equal(energy.flowRateText, "12");
  assert.equal(energy.capacityRateText, "12");
  assert.equal(energy.indicativeRatioPct, 100);

  const volume = build(
    {
      native_rate_json: rate("0.00024", "volume", "10", {
        unit_text: "m3/h",
        normalized_unit: "m3/hour",
        rate_basis: "hour",
      }),
    },
    {
      native_rate_json: rate("0.00012", "volume", "0.00012", {
        unit_text: "mcm/d",
        normalized_unit: "mcm/day",
        rate_basis: "day",
      }),
    },
  );
  assert.equal(volume.reasonCode, "indicated");
  assert.equal(volume.unit, "mcm/day");
  assert.equal(volume.flowRateText, "0.00024");
  assert.equal(volume.capacityRateText, "0.00012");
  assert.ok(volume.indicativeRatioPct !== null);
  assert.ok(Math.abs(volume.indicativeRatioPct - 200) < 1e-9);
});

test("volume uses the backend's mcm/day canonical field, never a client m3 conversion", () => {
  const context = build(
    {
      native_rate_json: rate("0.0125", "volume", "12500"),
    },
    {
      native_rate_json: rate("0.05", "volume", "50000"),
    },
  );
  assert.equal(context.reasonCode, "indicated");
  assert.equal(context.unit, "mcm/day");
  assert.equal(context.flowRateText, "0.0125");
  assert.equal(context.capacityRateText, "0.05");
  assert.equal(context.indicativeRatioPct, 25);
});

test("zero actual flow against positive capacity is a valid 0% indication", () => {
  const context = build({ native_rate_json: rate("0") });
  assert.equal(context.indicativeRatioPct, 0);
  assert.equal(context.reasonCode, "indicated");
  assert.equal(context.flowRateText, "0");
});

test("zero capacity is not treated as missing flow and never divides", () => {
  const context = build({}, { native_rate_json: rate("0") });
  assert.equal(context.indicativeRatioPct, null);
  assert.equal(context.reasonCode, "capacity_not_positive");
  assert.equal(context.capacityRateText, "0");
  assert.equal(context.flowRateText, "92954921");
});

test("negative flow is reported exactly but never made directional by Math.abs", () => {
  const context = build({ native_rate_json: rate("-123.45") });
  assert.equal(context.flowRateText, "-123.45");
  assert.equal(context.indicativeRatioPct, null);
  assert.equal(context.reasonCode, "negative_flow");
});

test("ratio above 100 remains unclipped and invents no headroom result", () => {
  const context = build(
    { native_rate_json: rate("200") },
    { native_rate_json: rate("100") },
  );
  assert.equal(context.reasonCode, "indicated");
  assert.equal(context.indicativeRatioPct, 200);
});

test("missing lineage or an unaware receipt suppresses the comparison", () => {
  const noLineage = build({ payload_sha256: "" });
  assert.equal(noLineage.reasonCode, "missing_flow_lineage");
  assert.equal(noLineage.indicativeRatioPct, null);

  const malformedHash = build({ payload_sha256: "not-a-sha256" });
  assert.equal(malformedHash.reasonCode, "missing_flow_lineage");

  const naiveObserved = build({ observed_at_utc: "2026-10-28T01:02:03" });
  assert.equal(naiveObserved.reasonCode, "missing_flow_receipt");
  assert.equal(naiveObserved.indicativeRatioPct, null);

  const capacityUnknownTime = build({}, { received_at_utc: "not-a-time" });
  assert.equal(capacityUnknownTime.reasonCode, "missing_capacity_receipt");
  assert.equal(capacityUnknownTime.indicativeRatioPct, null);
  assert.equal(capacityUnknownTime.capacityRateText, "416592000");
});

test("missing outer or nested normalizer metadata is not silently accepted", () => {
  const outerMissing = build({ normalizer_version: "" });
  assert.equal(outerMissing.reasonCode, "missing_flow_metadata");
  assert.equal(outerMissing.indicativeRatioPct, null);

  const nestedMissing = build({
    native_rate_json: rate("92954921", "energy", "92954921", {
      normalizer_version: "",
    }),
  });
  assert.equal(nestedMissing.reasonCode, "missing_flow_metadata");

  const wrongVersion = build({ normalizer_version: "entsog-native-units-v2" });
  assert.equal(wrongVersion.reasonCode, "flow_source_not_entsog_v1");

  const wrongSource = build({ source_system: "OTHER" });
  assert.equal(wrongSource.reasonCode, "flow_source_not_entsog_v1");
});

test("naive, impossible and reversed periods are refused", () => {
  const naive = build({ period_start_utc: "2026-10-28T00:00:00" });
  assert.equal(naive.reasonCode, "invalid_flow_period");
  assert.equal(naive.indicativeRatioPct, null);

  const reversed = build({ period_end_utc: FLOW_START });
  assert.equal(reversed.reasonCode, "invalid_flow_period");

  const impossible = build({ period_start_utc: "2026-02-30T00:00:00+00:00" });
  assert.equal(impossible.reasonCode, "invalid_flow_period");
});

test("stable period/id ordering does not mutate the input arrays", () => {
  const late = flow({
    observation_id: "entsog-flow-n1-late",
    period_start_utc: "2026-10-30T00:00:00+00:00",
    period_end_utc: "2026-10-31T00:00:00+00:00",
  });
  const first = flow({
    observation_id: "entsog-flow-n1-first",
    period_start_utc: FLOW_START,
    period_end_utc: FLOW_END,
  });
  const flows = [late, first];
  const contexts = buildNativeCapacityContext(flows as never, [capacity()] as never);
  assert.deepEqual(
    contexts.map((context) => context.flow.observation_id),
    ["entsog-flow-n1-first", "entsog-flow-n1-late"],
  );
  assert.deepEqual(
    flows.map((item) => item.observation_id),
    ["entsog-flow-n1-late", "entsog-flow-n1-first"],
  );
});

test("inputs and their references are left untouched", () => {
  const inputFlow = deepFreeze(flow({
    native_rate_json: rate("92954921.1234567890123456789"),
  }));
  const inputCapacity = deepFreeze(capacity({
    native_rate_json: rate("416592000.9876543210987654321"),
  }));
  const flowSnapshot = structuredClone(inputFlow);
  const capacitySnapshot = structuredClone(inputCapacity);

  const contexts = buildNativeCapacityContext(
    [inputFlow] as never,
    [inputCapacity] as never,
  );
  assert.equal(contexts.length, 1);
  assert.equal(contexts[0]?.flow, inputFlow);
  assert.equal(contexts[0]?.capacity, inputCapacity);
  assert.deepEqual(inputFlow, flowSnapshot);
  assert.deepEqual(inputCapacity, capacitySnapshot);
});

test("more than the supported rows throws instead of truncating", () => {
  const tooMany = Array.from(
    { length: NATIVE_CAPACITY_MAX_OBSERVATIONS + 1 },
    () => flow(),
  );
  assert.throws(
    () => buildNativeCapacityContext(tooMany as never, [] as never),
    RangeError,
  );
  assert.throws(
    () => buildNativeCapacityContext([flow()] as never, tooMany as never),
    RangeError,
  );
});
