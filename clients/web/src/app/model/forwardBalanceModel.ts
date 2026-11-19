/**
 * The forward balance (CP-25) as the page reads it: the one-line headline, the two charts
 * (balance by source against demand; the implied storage path against its band) and the
 * table rows, from `GET /api/fundamentals/forward-balance`. Pure, so it is tested with
 * `node --test`.
 */
import type { ForwardBalanceDTO } from "../../api/client.ts";
import type { ChartData } from "../../components/ui/charts/chartModel.ts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface Phrase {
  key: string;
  values: Record<string, string | number>;
}

function whole(value: number): string {
  return Math.round(value).toLocaleString("en-GB");
}

/** "Tighter than normal by 284 GWh/d over the next 14 days, mainly because demand runs above normal." */
export function headlinePhrase(dto: ForwardBalanceDTO | null): Phrase | null {
  const headline = dto?.headline;
  if (!headline) return null;
  const share = headline.contributions_gwh_d[headline.main_driver];
  // A positive contribution tightens: demand above normal, or a supply line below normal.
  const tightens = share > 0;
  const driver =
    headline.main_driver === "demand"
      ? tightens ? "fb.driver.demand_above" : "fb.driver.demand_below"
      : headline.main_driver === "norway"
        ? tightens
          ? headline.norway_outage_gwh_d > 0 ? "fb.driver.norway_below_outage" : "fb.driver.norway_below"
          : "fb.driver.norway_above"
        : tightens ? "fb.driver.lng_below" : "fb.driver.lng_above";
  return {
    key: `fb.headline.${headline.direction}`,
    values: {
      gwh: whole(headline.gwh_d),
      days: headline.window.days,
      driver,
      share: whole(Math.abs(share)),
      outage: whole(headline.norway_outage_gwh_d),
    },
  };
}

/** Supply by source against demand, D+1..D+14 (GWh/d); demand's normal as a grey line. */
export function balanceChart(dto: ForwardBalanceDTO, t: Translate): ChartData {
  const days = dto.daily;
  const simulated = dto.simulated;
  return {
    axis: "gas-day",
    x: days.map((row) => row.day),
    xTitle: t("chart.gas_day"),
    unit: dto.unit,
    series: [
      { id: "norway", label: t("nwe.norway"), values: days.map((r) => r.norway_gwh_d), style: "bar", stack: true, colour: 1, forecastFrom: 0, simulated, decimals: 0 },
      { id: "lng", label: t("nwe.lng"), values: days.map((r) => r.lng_gwh_d), style: "bar", stack: true, colour: 2, forecastFrom: 0, simulated, decimals: 0 },
      { id: "storage", label: t("fb.storage_draw"), values: days.map((r) => r.storage_gwh_d), style: "bar", stack: true, colour: 3, forecastFrom: 0, simulated, decimals: 0 },
      { id: "demand", label: t("fb.demand"), values: days.map((r) => r.demand_gwh_d), style: "line", colour: 4, forecastFrom: 0, simulated, decimals: 0 },
      { id: "demand_normal", label: t("fb.demand_normal"), values: days.map((r) => r.demand_normal_gwh_d), style: "line", ghost: true, decimals: 0 },
    ],
  };
}

/** The last day of a "YYYY-MM" month as a gas day. */
export function monthEnd(month: string): string {
  const [year, mon] = month.split("-").map(Number);
  const last = new Date(Date.UTC(year, mon, 0)).getUTCDate();
  return `${month}-${String(last).padStart(2, "0")}`;
}

/** Fill % at D+1, D+14 and each month's end, against the band and the target. */
export function storageChart(dto: ForwardBalanceDTO, t: Translate): ChartData | null {
  const points = [
    // The first and last forecast day, then month ends: daily points beside monthly ones
    // would crowd the axis without adding a turn in the path.
    ...dto.daily
      .filter((_, index) => index === 0 || index === dto.daily.length - 1)
      .map((r) => ({ day: r.day, fill: r.fill_pct, low: r.band_low_pct, high: r.band_high_pct, mean: r.band_mean_pct })),
    ...dto.monthly.map((m) => ({ day: monthEnd(m.month), fill: m.fill_pct_end, low: m.band_low_pct, high: m.band_high_pct, mean: m.band_mean_pct })),
  ];
  if (!points.some((p) => p.fill != null)) return null;
  const band = dto.storage.band_label && points.some((p) => p.low != null)
    ? [{ id: "band", label: dto.storage.band_label, years: [], low: points.map((p) => p.low), high: points.map((p) => p.high), mean: points.map((p) => p.mean), meanLabel: t("fb.band_mean") }]
    : undefined;
  const target = dto.storage.target;
  return {
    axis: "gas-day",
    x: points.map((p) => p.day),
    xTitle: t("chart.gas_day"),
    unit: "%",
    series: [
      { id: "fill", label: t("fb.implied_fill"), values: points.map((p) => p.fill), style: "line", colour: 1, forecastFrom: 0, simulated: dto.simulated, decimals: 1 },
    ],
    bands: band,
    rules: target ? [{ id: "target", value: target.pct, label: t("fb.target_rule", { pct: target.pct }), kind: "target" }] : undefined,
  };
}

export interface ForwardRow {
  key: string;
  period: string;
  kind: "day" | "month";
  demand: number;
  error: number | null;
  normal: number | null;
  norway: number;
  outage: number;
  lng: number;
  storage: number;
  gap: number;
  fill: number | null;
  bandLow: number | null;
  bandHigh: number | null;
}

/** The table: the 14 days, then the months; each month's fill is its month-end fill. */
export function forwardRows(dto: ForwardBalanceDTO | null): ForwardRow[] {
  if (!dto) return [];
  return [
    ...dto.daily.map((r) => ({
      key: `d-${r.day}`, period: r.day, kind: "day" as const, demand: r.demand_gwh_d, error: r.demand_error_gwh_d,
      normal: r.demand_normal_gwh_d, norway: r.norway_gwh_d, outage: r.norway_outage_gwh_d, lng: r.lng_gwh_d,
      storage: r.storage_gwh_d, gap: r.gap_gwh_d, fill: r.fill_pct, bandLow: r.band_low_pct, bandHigh: r.band_high_pct,
    })),
    ...dto.monthly.map((m) => ({
      key: `m-${m.month}`, period: m.month, kind: "month" as const, demand: m.demand_gwh_d, error: m.demand_error_gwh_d,
      normal: null, norway: m.norway_gwh_d, outage: m.norway_outage_gwh_d, lng: m.lng_gwh_d,
      storage: m.storage_gwh_d, gap: m.gap_gwh_d, fill: m.fill_pct_end, bandLow: m.band_low_pct, bandHigh: m.band_high_pct,
    })),
  ];
}

/** Where the fill sits against its band: "below", "within" or "above" (null without a band). */
export function bandPosition(fill: number | null, low: number | null, high: number | null): "below" | "within" | "above" | null {
  if (fill == null || low == null || high == null) return null;
  if (fill < low) return "below";
  if (fill > high) return "above";
  return "within";
}
