/**
 * What a shadow run's economics rest on (slice B of the D3 decision, completed by the owner's
 * decision on the unmounted terminal).
 *
 * The shadow task's monitor management answers *what is happening* - monitors, alerts, drift,
 * evaluations, lifecycle. What no mounted surface answered is *what the run's economics rest on*:
 * which price basis each figure came from, whether that basis is simulated or stale, what the pool
 * actually costs, how much daily PnL each basis puts at risk, and which engine, dataset and commit
 * produced the run being read.
 *
 * That presentation existed in `StrategyShadowRunTerminal.tsx`, a 838-line component nothing
 * rendered. The owner's decision was to keep the content and retire the parallel shell, so the
 * derivations moved here - pure functions over the reads the client already holds - and the panels
 * moved into the shadow task itself. Nothing here invents a number: a basis with no observation
 * keeps `null` and is counted as unavailable, and a margin against an unknown pool cost is `null`
 * rather than the latest price.
 */

import type {
  FxRateDTO,
  NormalizedMarketObsDTO,
  PortfolioResourceDTO,
  StrategyLabResultDTO,
  StrategyPriceObservationDTO,
  StrategyRunDTO,
} from "@/api/client";

type Translate = (key: string) => string;

export type PriceBasisId =
  | "WITHIN_DAY"
  | "DAY_AHEAD"
  | "MONTHLY"
  | "ICIS_ASSESSMENT"
  | "ICE_OCM_MARK"
  | "EEX_CURVE"
  | "FX";

export interface StrategyPriceBasisRow {
  basis: PriceBasisId;
  latestPrice: number | null;
  observationCount: number;
  sourceSystems: string[];
  simulatedCount: number;
  staleCount: number;
  latestObservedAtUtc: string | null;
}

export interface StrategyPnlCurveRow {
  basis: PriceBasisId;
  latestPrice: number | null;
  pnlGbpPerDay: number | null;
  marginGbpMwh: number | null;
  poolQuantityMwhPerDay: number;
  weightedPoolCostGbpMwh: number | null;
  sourceSystems: string[];
  simulatedCount: number;
  staleCount: number;
}

export interface StrategyBasisExposureRow {
  basis: PriceBasisId;
  latestPrice: number | null;
  basisMarginVsPoolCost: number | null;
  poolPnlAtRiskGbpPerDay: number | null;
  poolQuantityMwhPerDay: number;
  weightedPoolCostGbpMwh: number | null;
  observationCount: number;
  sourceSystems: string[];
  simulatedCount: number;
  staleCount: number;
}

export interface StrategyContractPnlRow {
  resourceId: string;
  resourceName: string;
  quantityMwhPerDay: number;
  costGbpMwh: number;
  marginGbpMwh: number | null;
  dailyPnlGbp: number | null;
}

export interface StrategyPoolRow {
  resourceId: string;
  resourceName: string;
  quantityMwhPerDay: number;
  costGbpMwh: number;
}

/** The bases a price can belong to, in the order the board presents them. */
export const PRICE_BASIS_ORDER: readonly PriceBasisId[] = [
  "WITHIN_DAY",
  "DAY_AHEAD",
  "MONTHLY",
  "ICIS_ASSESSMENT",
  "ICE_OCM_MARK",
  "EEX_CURVE",
  "FX",
];

/**
 * How old an observation of each basis may be before the board marks it stale.
 *
 * These are presentation thresholds, not data quality measures: the platform's own freshness
 * vocabulary lives in the source-posture rows, and this table exists so a trader reading the board
 * knows which figure is a live quote and which is last month's curve.
 */
export const STALE_HOURS_BY_BASIS: Readonly<Record<PriceBasisId, number>> = {
  WITHIN_DAY: 2,
  DAY_AHEAD: 36,
  MONTHLY: 120,
  ICIS_ASSESSMENT: 72,
  ICE_OCM_MARK: 2,
  EEX_CURVE: 24,
  FX: 72,
};

export function basisLabelKey(basis: PriceBasisId): string {
  return `strategy.basis.${basis.toLowerCase()}`;
}

export function observedAtMs(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function isSimulatedSource(sourceSystem: string | null | undefined): boolean {
  return Boolean(sourceSystem?.toUpperCase().includes("_SIM"));
}

export function isStaleObservation(
  observedAtUtc: string | null | undefined,
  maxAgeHours: number,
  nowMs: number,
): boolean {
  const observedMs = observedAtMs(observedAtUtc);
  // An observation with no readable instant cannot be shown to be current, so it is stale - which
  // is a statement about the evidence, not about the price.
  if (observedMs <= 0) return true;
  return nowMs - observedMs > maxAgeHours * 60 * 60 * 1000;
}

export function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

/** A governed market observation as a strategy price observation, or null when it is not a price. */
export function tapePriceFromMarketObservation(
  item: NormalizedMarketObsDTO,
): StrategyPriceObservationDTO | null {
  if (!item.is_gas_price || item.price_gbp_mwh === null) return null;
  return {
    observation_id: item.observation_id,
    source_system: item.source_system ?? "market-observation",
    venue: item.market_venue,
    hub: item.hub,
    product: item.product,
    price_name: item.product,
    price_gbp_mwh: item.price_gbp_mwh,
    observed_at_utc: item.observed_at_utc ?? item.period_start_utc,
    delivery_start_utc: item.period_start_utc,
    delivery_end_utc: item.period_end_utc,
    source_reference: item.source_reference,
  };
}

function sourceHaystack(price: StrategyPriceObservationDTO): string {
  return [
    price.source_system,
    price.venue,
    price.hub,
    price.product,
    price.price_name,
    price.source_reference ?? "",
  ]
    .join(" ")
    .toUpperCase();
}

export function classifyPriceBasis(price: StrategyPriceObservationDTO): PriceBasisId {
  const haystack = sourceHaystack(price);
  if (haystack.includes("ICIS")) return "ICIS_ASSESSMENT";
  if (haystack.includes("ICE_OCM") || haystack.includes("ICE OCM")) return "ICE_OCM_MARK";
  if (haystack.includes("EEX") || haystack.includes("CURVE") || haystack.includes("FUTURE")) {
    return "EEX_CURVE";
  }
  if (haystack.includes("MONTH") || haystack.includes("M+")) return "MONTHLY";
  if (haystack.includes("WITHIN") || haystack.includes("INTRADAY")) return "WITHIN_DAY";
  return "DAY_AHEAD";
}

export function priceMatchesBasis(
  price: StrategyPriceObservationDTO,
  basis: PriceBasisId,
): boolean {
  const haystack = sourceHaystack(price);
  if (basis === "FX") return false;
  if (classifyPriceBasis(price) === basis) return true;
  if (basis === "WITHIN_DAY") return haystack.includes("WITHIN") || haystack.includes("INTRADAY");
  if (basis === "DAY_AHEAD") {
    return (
      haystack.includes("DAY-AHEAD") || haystack.includes("DAY AHEAD") || haystack.includes("SAP")
    );
  }
  if (basis === "MONTHLY") return haystack.includes("MONTH") || haystack.includes("M+");
  if (basis === "ICIS_ASSESSMENT") return haystack.includes("ICIS") || haystack.includes("HEREN");
  if (basis === "ICE_OCM_MARK") {
    return haystack.includes("ICE_OCM") || haystack.includes("ICE OCM") || haystack.includes("OCM");
  }
  return haystack.includes("EEX") || haystack.includes("CURVE") || haystack.includes("FUTURE");
}

export function latestPriceObservation(
  observations: readonly StrategyPriceObservationDTO[],
): StrategyPriceObservationDTO | null {
  return observations.reduce<StrategyPriceObservationDTO | null>((latest, observation) => {
    if (!latest) return observation;
    return observedAtMs(observation.observed_at_utc) > observedAtMs(latest.observed_at_utc)
      ? observation
      : latest;
  }, null);
}

/** The price tape the client holds: the scenario's own observations, then the market read. */
export function priceTape(
  scenarioPrices: readonly StrategyPriceObservationDTO[],
  marketObservations: readonly NormalizedMarketObsDTO[],
): StrategyPriceObservationDTO[] {
  const observed = [
    ...scenarioPrices,
    ...marketObservations
      .map((item) => tapePriceFromMarketObservation(item))
      .filter((item): item is StrategyPriceObservationDTO => item !== null),
  ];
  const seen = new Set<string>();
  return observed
    .filter((price) => {
      const key = `${price.observation_id}:${price.source_system}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort(
      (left, right) =>
        observedAtMs(right.observed_at_utc) - observedAtMs(left.observed_at_utc),
    );
}

/**
 * One row per basis, always all seven.
 *
 * A basis with nothing observed keeps `latestPrice: null` and `observationCount: 0`, which the
 * board renders as unavailable - the row is not dropped, because "this deployment has no EEX curve
 * today" is a fact a trader needs, and a missing row would read as a basis that does not exist.
 *
 * `staleCount` is a freshness statement about the figure the board shows, not a tally of the
 * archive: a basis is stale when the **latest** observation of it is older than that basis's
 * threshold (or carries no readable instant). Counting every stale row behind the latest price
 * would mark a live quote stale because last month's observations are old, which is exactly the
 * drift the contract test `test_strategy_freshness_uses_latest_observation_per_basis` forbids.
 */
export function priceBasisRows(input: {
  readonly tape: readonly StrategyPriceObservationDTO[];
  readonly fxRates: readonly FxRateDTO[];
  readonly nowMs: number;
}): StrategyPriceBasisRow[] {
  return PRICE_BASIS_ORDER.map((basis) => {
    if (basis === "FX") {
      const latestFx = input.fxRates.reduce<FxRateDTO | null>((latest, rate) => {
        if (!latest) return rate;
        return observedAtMs(rate.observed_at_utc) > observedAtMs(latest.observed_at_utc)
          ? rate
          : latest;
      }, null);
      return {
        basis,
        latestPrice: latestFx?.rate ?? null,
        observationCount: input.fxRates.length,
        sourceSystems: uniqueStrings(input.fxRates.map((rate) => rate.source_system)),
        simulatedCount: input.fxRates.filter((rate) => isSimulatedSource(rate.source_system))
          .length,
        staleCount:
          latestFx &&
          isStaleObservation(
            latestFx.observed_at_utc,
            STALE_HOURS_BY_BASIS.FX,
            input.nowMs,
          )
            ? 1
            : 0,
        latestObservedAtUtc: latestFx?.observed_at_utc ?? null,
      };
    }
    const observations = input.tape.filter((price) => priceMatchesBasis(price, basis));
    const latest = latestPriceObservation(observations);
    return {
      basis,
      latestPrice: latest?.price_gbp_mwh ?? null,
      observationCount: observations.length,
      sourceSystems: uniqueStrings(observations.map((price) => price.source_system)),
      simulatedCount: observations.filter((price) => isSimulatedSource(price.source_system)).length,
      staleCount:
        latest &&
        isStaleObservation(
          latest.observed_at_utc,
          STALE_HOURS_BY_BASIS[basis],
          input.nowMs,
        )
          ? 1
          : 0,
      latestObservedAtUtc: latest?.observed_at_utc ?? null,
    };
  });
}

/** The pool's resources, with the all-in cost each one carries. */
export function poolRows(
  resources: readonly PortfolioResourceDTO[],
): StrategyPoolRow[] {
  return resources.map((resource) => ({
    resourceId: resource.resource_id,
    resourceName: resource.resource_name,
    quantityMwhPerDay: resource.available_quantity_mwh_per_day,
    costGbpMwh:
      resource.contract_cost_gbp_mwh +
      (resource.variable_cost_gbp_mwh ?? 0) +
      (resource.tolerance_risk_allowance_gbp_mwh ?? 0),
  }));
}

export function poolQuantity(rows: readonly StrategyPoolRow[]): number {
  return rows.reduce((total, row) => total + row.quantityMwhPerDay, 0);
}

/** The volume-weighted pool cost, or null when there is no volume to weight it by. */
export function weightedPoolCost(rows: readonly StrategyPoolRow[]): number | null {
  const quantity = poolQuantity(rows);
  if (quantity <= 0) return null;
  return (
    rows.reduce((total, row) => total + row.quantityMwhPerDay * row.costGbpMwh, 0) / quantity
  );
}

/**
 * The daily PnL each basis would carry if the pool were sold at that basis's latest price.
 *
 * A basis with no price, or a pool with no cost, produces `null` - never a zero, which would read
 * as a measured break-even.
 */
export function pnlCurveRows(
  basisRows: readonly StrategyPriceBasisRow[],
  pool: { readonly quantityMwhPerDay: number; readonly weightedCostGbpMwh: number | null },
): StrategyPnlCurveRow[] {
  return basisRows
    .filter((row) => row.basis !== "FX")
    .map((row) => {
      const margin =
        row.latestPrice !== null && pool.weightedCostGbpMwh !== null
          ? row.latestPrice - pool.weightedCostGbpMwh
          : null;
      return {
        basis: row.basis,
        latestPrice: row.latestPrice,
        marginGbpMwh: margin,
        pnlGbpPerDay:
          margin !== null && pool.quantityMwhPerDay > 0 ? margin * pool.quantityMwhPerDay : null,
        poolQuantityMwhPerDay: pool.quantityMwhPerDay,
        weightedPoolCostGbpMwh: pool.weightedCostGbpMwh,
        sourceSystems: row.sourceSystems,
        simulatedCount: row.simulatedCount,
        staleCount: row.staleCount,
      };
    });
}

export function basisExposureRows(
  pnlRows: readonly StrategyPnlCurveRow[],
  basisRows: readonly StrategyPriceBasisRow[],
): StrategyBasisExposureRow[] {
  return pnlRows.map((row) => ({
    basis: row.basis,
    latestPrice: row.latestPrice,
    basisMarginVsPoolCost: row.marginGbpMwh,
    poolPnlAtRiskGbpPerDay: row.pnlGbpPerDay,
    poolQuantityMwhPerDay: row.poolQuantityMwhPerDay,
    weightedPoolCostGbpMwh: row.weightedPoolCostGbpMwh,
    observationCount:
      basisRows.find((basisRow) => basisRow.basis === row.basis)?.observationCount ?? 0,
    sourceSystems: row.sourceSystems,
    simulatedCount: row.simulatedCount,
    staleCount: row.staleCount,
  }));
}

export function contractPnlRows(
  rows: readonly StrategyPoolRow[],
  activeSalePrice: number | null,
): StrategyContractPnlRow[] {
  return rows.map((resource) => {
    const marginGbpMwh =
      activeSalePrice !== null ? activeSalePrice - resource.costGbpMwh : null;
    return {
      ...resource,
      marginGbpMwh,
      dailyPnlGbp: marginGbpMwh !== null ? marginGbpMwh * resource.quantityMwhPerDay : null,
    };
  });
}

export function maxAbsPnl(rows: readonly StrategyPnlCurveRow[]): number {
  return Math.max(
    ...rows.map((row) => Math.abs(row.pnlGbpPerDay ?? 0)).filter((value) => Number.isFinite(value)),
    1,
  );
}

export function basisCounts(rows: readonly StrategyPriceBasisRow[]): {
  simulated: number;
  stale: number;
  unavailable: number;
} {
  return {
    simulated: rows.filter((row) => row.simulatedCount > 0).length,
    stale: rows.filter((row) => row.staleCount > 0).length,
    unavailable: rows.filter((row) => row.observationCount === 0).length,
  };
}

/** The most recent run in a set, by the instant it started. */
export function latestRun(runs: readonly StrategyRunDTO[]): StrategyRunDTO | null {
  return runs.reduce<StrategyRunDTO | null>((latest, run) => {
    if (!latest) return run;
    return observedAtMs(run.started_at_utc) > observedAtMs(latest.started_at_utc) ? run : latest;
  }, null);
}

export interface ShadowRunProvenance {
  readonly run: StrategyRunDTO | null;
  /** Whether the last evaluated result, or the latest persisted run, asked for a human review. */
  readonly humanReviewRequired: boolean;
  readonly missingInputs: readonly string[];
  readonly warnings: readonly string[];
  readonly sourceRefs: readonly string[];
  /** What the run proposes, as the engine reported it, or null when it reported none. */
  readonly candidateAction: string | null;
}

/**
 * The provenance of what the surface is showing.
 *
 * The evaluated result is preferred over the latest persisted run because it is what the operator
 * just asked for; the run supplies the engine, dataset and commit behind it. A missing input or a
 * warning from either is kept, and `HUMAN_REVIEW_REQUIRED` is added when either asks for review, so
 * the panel cannot show a figure without the boundary it carries.
 */
export function shadowRunProvenance(input: {
  readonly result: StrategyLabResultDTO | null;
  readonly runs: readonly StrategyRunDTO[];
}): ShadowRunProvenance {
  const run = latestRun(input.runs);
  const humanReviewRequired =
    input.result?.human_review_required ?? run?.human_review_required ?? false;
  const warnings = [
    ...(input.result?.missing_inputs ?? run?.missing_inputs ?? []),
    ...(input.result?.warnings ?? run?.warnings ?? []),
    ...(humanReviewRequired ? ["HUMAN_REVIEW_REQUIRED"] : []),
  ];
  return {
    run,
    humanReviewRequired,
    missingInputs: input.result?.missing_inputs ?? run?.missing_inputs ?? [],
    warnings,
    sourceRefs:
      input.result?.source_refs.length
        ? input.result.source_refs
        : (run?.source_refs ?? []),
    candidateAction: input.result?.candidate_action_for_review ?? null,
  };
}

/**
 * A warning code as prose, keeping the detail the engine attached to it.
 *
 * The vocabulary names a key per code (`strategy.warning.<code>`); a code the client's vocabulary
 * does not cover yet still reads as prose, because a raw `SOMETHING_FAILED: detail` tells the user
 * nothing they can act on.
 */
export function strategyWarningLabel(warning: string, t: Translate): string {
  const code = warning.split(":", 1)[0].trim().toLowerCase();
  const key = `strategy.warning.${code}`;
  const translated = t(key);
  if (translated !== key) {
    const detail = warning.includes(":") ? warning.slice(warning.indexOf(":") + 1).trim() : "";
    return detail ? `${translated}: ${detail}` : translated;
  }
  return warning.replaceAll("_", " ");
}
