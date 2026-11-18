/**
 * "Storage by country" (CP-04): what the panel shows, from `GET /api/fundamentals/storage`,
 * with nothing recomputed but the drawing. Pure; tested in tests/storageByCountry.test.ts.
 *
 * - The seasonal chart of one entity (the chart standard's season axis, F.1/F.2): this gas
 *   year in the accent, last year as a grey ghost, the history as the server drew it (a 5-yr
 *   range and its mean, or each held year as a grey line, or nothing with "history from"),
 *   and the EU target as a labelled rule where it applies. The band's label is the server's,
 *   so it never claims more years than the band is drawn from.
 * - The headline of a row: "71.4 % · −6.2 vs 5-yr · −0.31/d" (fill, against the N-yr mean,
 *   the day change in points).
 */
import type { StorageEntityDTO } from "../../api/client.ts";
import { formatSigned, type ChartComparison, type ChartData, type ChartSeries } from "../../components/ui/charts/chartModel.ts";

export interface SeasonLabels {
  lastYear: (gasYear: string) => string;
  thisYear: (gasYear: string) => string;
  mean: (years: number) => string;
  target: (pct: number) => string;
  xTitle: string;
}

export interface SeasonChart {
  data: ChartData;
  /** The history in words: the band's label, "N prior years held", or "history from …". */
  subtitle: string;
  /** The readout's comparison: this year against the band's mean, when there is a band. */
  compare?: ChartComparison;
}

/** What the seasonal chart needs of an entity: storage fill or LNG send-out alike. */
export interface SeasonEntity {
  simulated: boolean;
  history: { label: string };
  target?: { pct: number } | null;
  season?: StorageEntityDTO["season"];
}

export function seasonChart(entity: SeasonEntity, labels: SeasonLabels, compareLabel: string, unit = "%"): SeasonChart | null {
  const season = entity.season;
  if (!season) return null;
  const sim = entity.simulated;
  const series: ChartSeries[] = [
    ...season.lines.map((line) => ({ id: `y-${line.gas_year}`, label: line.gas_year, values: line.values, ghost: true, decimals: 1, simulated: sim })),
    ...(season.last_year
      ? [{ id: "last", label: labels.lastYear(season.last_year.gas_year), values: season.last_year.values, ghost: true, decimals: 1, simulated: sim }]
      : []),
    { id: "this", label: labels.thisYear(season.gas_year), values: season.this_year, colour: 1, decimals: 1, simulated: sim },
  ];
  const band = season.band;
  const data: ChartData = {
    axis: "season",
    x: season.axis,
    xTitle: labels.xTitle,
    unit,
    series,
    bands: band
      ? [{ id: "range", label: band.label, meanLabel: labels.mean(band.years.length), years: band.years, low: band.low, high: band.high, mean: band.mean }]
      : [],
    rules: entity.target ? [{ id: "target", value: entity.target.pct, label: labels.target(entity.target.pct), kind: "target" }] : [],
  };
  return {
    data,
    subtitle: entity.history.label,
    compare: band ? { series: "this", against: "range", label: compareLabel } : { series: "this", against: "last", label: compareLabel },
  };
}

/** "−6.2 vs 5-yr": the difference against the N-yr mean with N stated, or null. */
export function versusAverage(entity: StorageEntityDTO, words: (years: number) => string): string | null {
  const average = entity.vs_average;
  if (average.diff_pts == null || !average.years) return null;
  return `${formatSigned(average.diff_pts, 1)} ${words(average.years)}`;
}

/** "71.4 % · −6.2 vs 5-yr · −0.31/d": the headline of a country row or panel. */
export function headline(entity: StorageEntityDTO, words: (years: number) => string, perDay: string): string {
  const parts = [entity.fill_pct == null ? "–" : `${entity.fill_pct.toFixed(1)} %`];
  const average = versusAverage(entity, words);
  if (average) parts.push(average);
  if (entity.day_change_pts != null) parts.push(`${formatSigned(entity.day_change_pts, 2)}${perDay}`);
  return parts.join(" · ");
}

/** The sparkline's values and days, oldest first. */
export function sparkOf(entity: StorageEntityDTO): { values: (number | null)[]; days: string[] } {
  return { values: entity.spark.map((point) => point.fill_pct), days: entity.spark.map((point) => point.day) };
}

/** The codes whose seasonal series the panel asks for: the region and the selected country. */
export function seasonCodes(regionCode: string, selected: string | null): string[] {
  return selected && selected !== regionCode ? [regionCode, selected] : [regionCode];
}
