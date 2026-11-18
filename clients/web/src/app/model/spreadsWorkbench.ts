/**
 * Research → Spreads: the StrategySpec edits the "Understood as" chips make, the answers to the
 * server's questions, and the chart and waterfall built from a result. Pure functions: the
 * server holds every factor and computes every figure; this only rearranges what it returned.
 */

import type { CurveResultDTO, CurveRowDTO, HistoryResultDTO, InputClass, SpecIssueDTO, StrategySpecDTO } from "../../api/spreads.ts";

/** Weakest first (design basis 2, B.2): the result is as good as its weakest input. */
export const CLASS_ORDER: readonly InputClass[] = ["missing", "simulated", "assumption", "indicative", "derived", "converted", "reference", "sourced"];
export const DISPLAY_UNITS = ["EUR/MWh", "p/th", "USD/MMBtu", "GBP/MWh"] as const;

/** The view Spreads opens on: NBP over TTF by delivery month, net of the TTF → NBP route. */
export function defaultSpec(hubs: readonly string[]): StrategySpecDTO {
  const sell = hubs.includes("NBP") ? "NBP" : hubs.find((hub) => hub !== "TTF") ?? "NBP";
  return {
    version: 1,
    kind: "curve",
    legs: [
      { hub: sell, tenor: null, weight: 1 },
      { hub: "TTF", tenor: null, weight: -1 },
    ],
    unit: "EUR/MWh",
    fx: "forward",
    cost: { kind: "route_tariff", from_hub: "TTF", to_hub: sell },
    rule: null,
    lookback_days: 365,
    volume_mwh_per_day: null,
  };
}

function withLegs(spec: StrategySpecDTO, legs: StrategySpecDTO["legs"]): StrategySpecDTO {
  const hubs = new Set(legs.map((leg) => leg.hub));
  const cost = spec.cost && hubs.has(spec.cost.from_hub) && hubs.has(spec.cost.to_hub) ? spec.cost : null;
  return { ...spec, legs, cost };
}

/** Swap which leg is sold: the spread's sign and the route's direction turn round together. */
export function swapDirection(spec: StrategySpecDTO): StrategySpecDTO {
  return {
    ...spec,
    legs: spec.legs.map((leg) => ({ ...leg, weight: -leg.weight })),
    cost: spec.cost ? { ...spec.cost, from_hub: spec.cost.to_hub, to_hub: spec.cost.from_hub } : null,
  };
}

/** Replace one leg's hub; a route cost follows the hub it was attached to. */
export function setLegHub(spec: StrategySpecDTO, index: number, hub: string): StrategySpecDTO {
  const previous = spec.legs[index]?.hub;
  const legs = spec.legs.map((leg, at) => (at === index ? { ...leg, hub } : leg));
  const cost = spec.cost
    ? {
        ...spec.cost,
        from_hub: spec.cost.from_hub === previous ? hub : spec.cost.from_hub,
        to_hub: spec.cost.to_hub === previous ? hub : spec.cost.to_hub,
      }
    : null;
  return withLegs({ ...spec, cost }, legs);
}

export function setLegTenor(spec: StrategySpecDTO, index: number, tenor: string): StrategySpecDTO {
  return { ...spec, legs: spec.legs.map((leg, at) => (at === index ? { ...leg, tenor } : leg)) };
}

/** Curve or history; a history needs a tenor on each leg (the front month by default). */
export function setKind(spec: StrategySpecDTO, kind: StrategySpecDTO["kind"]): StrategySpecDTO {
  return {
    ...spec,
    kind,
    legs: spec.legs.map((leg) => ({ ...leg, tenor: kind === "history" ? leg.tenor ?? "M+1" : null })),
    rule: kind === "curve" ? null : spec.rule,
  };
}

/** Add the route tariff (from the bought leg to the sold one), or remove it. */
export function toggleCost(spec: StrategySpecDTO): StrategySpecDTO {
  if (spec.cost) return { ...spec, cost: null };
  const sell = [...spec.legs].sort((a, b) => b.weight - a.weight)[0];
  const buy = [...spec.legs].sort((a, b) => a.weight - b.weight)[0];
  if (!sell || !buy || sell.weight <= 0 || buy.weight >= 0) return spec;
  return { ...spec, cost: { kind: "route_tariff", from_hub: buy.hub, to_hub: sell.hub } };
}

/** The spec after the user answers one of the server's questions with one of its choices. */
export function applyChoice(spec: StrategySpecDTO, issue: SpecIssueDTO, choice: string): StrategySpecDTO {
  const leg = /^legs\[(\d+)\]/.exec(issue.field);
  const index = leg ? Number(leg[1]) : -1;
  switch (issue.code) {
    case "hub_not_held":
      return index >= 0 ? setLegHub(spec, index, choice) : spec;
    case "tenor_not_held":
      return index >= 0 ? setLegTenor(spec, index, choice) : spec;
    case "unit_unknown":
      return { ...spec, unit: choice };
    case "route_unproven":
    case "cost_hubs":
    case "cost_direction":
      return { ...spec, cost: null };
    case "no_curve":
    case "rule_needs_history":
      return setKind(spec, "history");
    case "history_short":
      return setKind(spec, "curve");
    case "kind_unknown":
      return setKind(spec, choice === "history" ? "history" : "curve");
    case "fx_mode":
      return { ...spec, fx: choice === "spot" ? "spot" : "forward" };
    default:
      return spec;
  }
}

/** "NBP − TTF": the spread as the desk writes it, sold leg first. */
export function spreadName(spec: StrategySpecDTO): string {
  const sorted = [...spec.legs].sort((a, b) => b.weight - a.weight);
  return sorted
    .map((leg, index) => {
      const sign = leg.weight < 0 ? "−" : index === 0 ? "" : "+";
      const size = Math.abs(leg.weight) === 1 ? "" : `${Math.abs(leg.weight)}×`;
      const tenor = leg.tenor ? ` ${leg.tenor}` : "";
      return `${sign}${sign ? " " : ""}${size}${leg.hub}${tenor}`;
    })
    .join(" ");
}

export function weakestClass(classes: readonly (InputClass | undefined | null)[]): InputClass {
  const found = classes.filter((item): item is InputClass => Boolean(item));
  if (found.length === 0) return "sourced";
  return found.reduce((weakest, item) => (CLASS_ORDER.indexOf(item) < CLASS_ORDER.indexOf(weakest) ? item : weakest));
}

/** Every input class a curve result rests on, weakest first, without repeats. */
export function curveClasses(result: CurveResultDTO): InputClass[] {
  const seen = new Set<InputClass>();
  for (const row of result.rows) {
    for (const leg of row.legs) {
      seen.add(leg.price_class);
      if (leg.fx) seen.add(leg.fx.input_class as InputClass);
    }
    if (row.cost_class) seen.add(row.cost_class);
    if (row.refused) seen.add("missing");
  }
  return [...seen].sort((a, b) => CLASS_ORDER.indexOf(a) - CLASS_ORDER.indexOf(b));
}

export interface CurveChartModel {
  x: string[];
  net: (number | null)[];
  gross: (number | null)[];
  hasCost: boolean;
  simulated: boolean;
}

/** The curve's points: net of the route cost as the line, gross as the grey context. */
export function curveChart(result: CurveResultDTO): CurveChartModel {
  const rows = result.rows.filter((row) => !row.refused);
  const hasCost = rows.some((row) => row.cost !== null && row.cost !== undefined);
  return {
    x: rows.map((row) => row.month.slice(0, 7)),
    net: rows.map((row) => (hasCost ? row.net : row.gross)),
    gross: rows.map((row) => row.gross),
    hasCost,
    simulated: result.simulated,
  };
}

export interface WaterfallLine {
  id: string;
  label: string;
  value: number;
  kind?: "total" | "delta";
}

/**
 * The front month as a waterfall: the gross spread, each
 * tariff leg (in the display unit, scaled from the route's own currency by the server's
 * conversion of the total), and the net. The steps reconcile to the server's net.
 */
export function frontWaterfall(
  result: CurveResultDTO,
  labels: { gross: string; net: string; leg: (hub: string) => string; tariff?: (tso: string, direction: string) => string },
): { row: CurveRowDTO; items: WaterfallLine[] } | null {
  const row = result.rows.find((item) => !item.refused && item.gross !== null);
  if (!row || row.gross === null) return null;
  // Starts at the gross spread: the legs' full prices would dwarf the costs being compared.
  void labels.leg;
  const items: WaterfallLine[] = [{ id: "gross", label: labels.gross, value: row.gross, kind: "total" }];
  const route = result.route;
  if (row.cost !== null && row.cost !== undefined && route && route.total) {
    const scale = row.cost / route.total;
    for (const [index, leg] of route.legs.entries()) {
      if (leg.value === null) continue;
      const label = labels.tariff ? labels.tariff(leg.tso, leg.direction) : `${leg.tso} ${leg.direction.toLowerCase()}`;
      items.push({ id: `tariff-${index}`, label, value: -leg.value * scale });
    }
    items.push({ id: "net", label: labels.net, value: row.net ?? row.gross - row.cost, kind: "total" });
  }
  return { row, items };
}

export interface HistoryChartModel {
  x: string[];
  spread: (number | null)[];
  rules: Array<{ id: string; value: number; label: string }>;
}

/** The daily spread with the route cost both ways as horizontal lines (D.2 route overlay). */
export function historyChart(result: HistoryResultDTO): HistoryChartModel {
  const points = result.analysis.points ?? [];
  const rules = (result.route?.lines ?? [])
    .filter((line) => line.value !== null && line.value !== undefined)
    .map((line, index) => ({ id: `route-${index}`, value: line.value as number, label: line.direction }));
  return { x: points.map((point) => point.date), spread: points.map((point) => point.spread), rules };
}

/** The description a link carries (`?workspace=research&task=spreads&describe=…`). */
export function describeFromSearch(search: string): string | null {
  const text = new URLSearchParams(search).get("describe");
  return text && text.trim().length >= 3 ? text.trim().slice(0, 4000) : null;
}

/** Interpretation stages shown while the server (and its model) works. */
export const INTERPRET_STAGES = ["spreads.progress.reading", "spreads.progress.matching", "spreads.progress.checking"] as const;
