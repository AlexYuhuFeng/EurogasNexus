/**
 * Prices → term structure of several hubs in one unit (design basis 2, F.3 #1): each hub's
 * curve in its own quotation is sent to the normalisation service (`POST /api/market/normalise`)
 * with its delivery month, so a p/th month is converted to EUR/MWh at the forward FX of that
 * month on the server. The client holds no factor and no rate; it lines the answers up by month.
 */

import type { NormaliseRequestDTO, NormaliseResponseDTO } from "../../api/comparablePrices.ts";

/** At most this many hubs on one term-structure chart (F.3 #1). */
export const MAX_COMPARED_HUBS = 3;
/** The unit several hubs are compared in. */
export const COMPARE_UNIT = "EUR/MWh";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2027-01" → "Jan-27": the product code the server resolves. */
export function monthCode(key: string): string | null {
  const match = /^(\d{4})-(\d{2})$/.exec(key);
  if (!match) return null;
  return `${MONTHS[Number(match[2]) - 1]}-${match[1].slice(2)}`;
}

export interface HubCurve {
  hub: string;
  months: readonly string[];
  values: readonly (number | null)[];
  unit: string;
}

/** The request that converts every held month of every hub curve to the compare unit. */
export function compareRequest(curves: readonly HubCurve[]): { body: NormaliseRequestDTO; keys: Array<{ hub: string; month: string }> } {
  const keys: Array<{ hub: string; month: string }> = [];
  const values: NormaliseRequestDTO["values"] = [];
  for (const curve of curves) {
    curve.months.forEach((month, index) => {
      const value = curve.values[index];
      const product = monthCode(month);
      if (value === null || value === undefined || !product) return;
      keys.push({ hub: curve.hub, month });
      values.push({ value, unit: curve.unit, product });
    });
  }
  return { body: { to_unit: COMPARE_UNIT, values }, keys };
}

export interface ComparedCurves {
  months: string[];
  series: Array<{ hub: string; values: (number | null)[] }>;
  /** The FX each converted hub used, as the server labels it ("derived (interest parity …)"). */
  fxLabels: string[];
  simulated: boolean;
  /** Months refused because they lie beyond the derived-forward horizon (D.5). */
  beyondHorizon: number;
  /** Any other reason a month was not converted, once each. */
  refused: string[];
}

/** The server's answers lined up by month, one series per hub; a refused month is a gap. */
export function comparedCurves(curves: readonly HubCurve[], keys: ReadonlyArray<{ hub: string; month: string }>, response: NormaliseResponseDTO): ComparedCurves {
  const months = [...new Set(curves.flatMap((curve) => [...curve.months]))].sort();
  const byKey = new Map<string, number | null>();
  const fxLabels = new Set<string>();
  const refused = new Set<string>();
  let beyondHorizon = 0;
  let simulated = false;
  keys.forEach((key, index) => {
    const answer = response.values[index];
    if (!answer) return;
    byKey.set(`${key.hub}:${key.month}`, answer.value ?? null);
    if (answer.refused?.code === "beyond_horizon") beyondHorizon += 1;
    else if (answer.refused) refused.add(answer.refused.message);
    if (answer.simulated) simulated = true;
    const fx = answer.normalisation?.fx;
    if (fx && fx.method !== "same currency") fxLabels.add(fx.label);
  });
  return {
    months,
    series: curves.map((curve) => ({ hub: curve.hub, values: months.map((month) => byKey.get(`${curve.hub}:${month}`) ?? null) })),
    fxLabels: [...fxLabels],
    simulated,
    beyondHorizon,
    refused: [...refused],
  };
}

/** The description Spreads interprets for the pair's spread by delivery month, net of transport. */
export function spreadsLink(search: string, hub: string): string {
  const other = hub === "TTF" ? "NBP" : hub;
  const next = new URLSearchParams(search);
  next.set("workspace", "research");
  next.set("task", "spreads");
  next.delete("view");
  next.set("describe", `forward spread net of transport tariff between TTF and ${other}`);
  return `?${next.toString()}`;
}
