/**
 * Desk → Board's detail panel (the pure part, tested in tests/traderBoard.test.ts): one chart
 * that follows what the trader last chose on the screen, and the series it draws.
 *
 * - a price cell: that contract today (intraday, yesterday's close as a reference line), or its
 *   daily closes over one month or one year;
 * - a hub's column head: its forward curve today against one day and one week ago;
 * - a spread: its last closes with its one-year range and the transport cost where it applies;
 * - a storage line: this gas year against the five-year band and last year; a flow or send-out
 *   line: its last 30 days.
 *
 * Every series comes from a read the product already makes; nothing is drawn that no source
 * holds (rule 17): a choice with no history is a "no source" state naming what would supply it.
 * Prices are put in the hub's quotation as the board is (NBP p/th).
 */
import type { MarketObsDTO, MarketQuoteDTO } from "../../api/client.ts";
import type { BoardTenorDTO } from "../../api/spreads.ts";
import type { BoardContract } from "./traderBoardModel.ts";
import { hubPriceUnit, inHubUnit } from "./traderBoardModel.ts";
import { quoteMid } from "./boardQuote.ts";

export type BoardSelection =
  | { kind: "price"; contract: string; hub: string }
  | { kind: "curve"; hub: string }
  | { kind: "spread"; pair: string; tenor: "DA" | "MA" }
  | { kind: "storage"; code: string }
  | { kind: "flow"; key: string };

/** The panel is never empty-looking: TTF's front month until the trader picks something. */
export const DEFAULT_SELECTION: BoardSelection = { kind: "price", contract: "M1", hub: "TTF" };

export type PriceRange = "intraday" | "1m" | "1y";

export function selectionKey(selection: BoardSelection): string {
  switch (selection.kind) {
    case "price":
      return `price:${selection.contract}:${selection.hub}`;
    case "curve":
      return `curve:${selection.hub}`;
    case "spread":
      return `spread:${selection.pair}:${selection.tenor}`;
    case "storage":
      return `storage:${selection.code}`;
    case "flow":
      return `flow:${selection.key}`;
  }
}

/**
 * The product name the observation store keeps a contract's closes under ("TTF month-ahead",
 * "NBP Q1-27"): the prompt products by their tenor word, the front month as month-ahead (its
 * longest series), the curve by the execution screen's label.
 */
export function historyProduct(contract: BoardContract, hub: string): string {
  const word: Record<string, string> = { wd: "within-day", da: "day-ahead", we: "weekend", bom: "BOM" };
  if (word[contract.kind]) return `${hub} ${word[contract.kind]}`;
  if (contract.key === "M1") return `${hub} month-ahead`;
  return `${hub} ${contract.label}`;
}

export interface PricePoint {
  at: string;
  value: number;
}

export interface PriceSeries {
  points: PricePoint[];
  unit: string;
  source: string | null;
  simulated: boolean;
  asOf: string | null;
}

function simulatedRow(row: MarketObsDTO): boolean {
  return /_sim$/i.test(row.source_system ?? "") || row.metadata_json?.simulated === true;
}

/**
 * The closes of one product in the hub's quotation, oldest first. Real rows win: once any real
 * row is held, simulated ones are left out, so the two never draw one line.
 */
export function observationSeries(rows: readonly MarketObsDTO[], hub: string): PriceSeries {
  const real = rows.some((row) => !simulatedRow(row));
  const kept = rows.filter((row) => (real ? !simulatedRow(row) : true));
  const points = kept
    .map((row) => ({ at: row.observed_at_utc ?? row.period_start_utc, value: inHubUnit(hub, row.price, row.currency, row.unit) }))
    .filter((point): point is PricePoint => point.value !== null && Boolean(point.at))
    .sort((a, b) => a.at.localeCompare(b.at));
  const newest = kept.slice().sort((a, b) => String(b.observed_at_utc ?? "").localeCompare(String(a.observed_at_utc ?? "")))[0];
  return {
    points,
    unit: hubPriceUnit(hub),
    source: newest?.source_system ?? null,
    simulated: kept.length > 0 && !real,
    asOf: points.length ? points[points.length - 1]!.at : null,
  };
}

/** The last close of each gas day (UTC date of the observation), oldest first. */
export function dailyCloses(points: readonly PricePoint[], sinceIso: string): PricePoint[] {
  const byDay = new Map<string, PricePoint>();
  for (const point of points) {
    if (point.at < sinceIso) continue;
    const day = point.at.slice(0, 10);
    const held = byDay.get(day);
    if (!held || point.at > held.at) byDay.set(day, point);
  }
  return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, point]) => ({ at: day, value: point.value }));
}

/**
 * Today's ticks of the product (observed on or after the gas day's start), with the board's
 * current quote mid appended when it is newer, so the line ends where the board stands.
 */
export function intradayPoints(points: readonly PricePoint[], gasDayStartIso: string, quote: MarketQuoteDTO | null, hub: string): PricePoint[] {
  const today = points.filter((point) => point.at >= gasDayStartIso);
  const mid = quote ? inHubUnit(hub, quoteMid(quote), quote.currency, quote.unit) : null;
  if (quote && mid !== null && quote.observed_at_utc >= gasDayStartIso && !today.some((point) => point.at >= quote.observed_at_utc)) {
    today.push({ at: quote.observed_at_utc, value: mid });
  }
  return today.sort((a, b) => a.at.localeCompare(b.at));
}

/** The previous close the intraday chart draws as its reference line, in the hub's quotation. */
export function referenceClose(points: readonly PricePoint[], gasDayStartIso: string, quote: MarketQuoteDTO | null, hub: string): number | null {
  const fromQuote = quote ? inHubUnit(hub, quote.close_price ?? null, quote.currency, quote.unit) : null;
  if (fromQuote !== null) return fromQuote;
  const before = points.filter((point) => point.at < gasDayStartIso);
  return before.length ? before[before.length - 1]!.value : null;
}

const MONTH_TENOR = /^\d{4}-\d{2}$/;

export interface CurveSnapshot {
  months: string[];
  today: (number | null)[];
  dayAgo: (number | null)[];
  weekAgo: (number | null)[];
  simulated: boolean;
  asOf: string | null;
  source: string | null;
}

/**
 * The hub's monthly curve as it stood at three instants: the newest held, one day and one week
 * before it. A month with no close held at an instant is a gap, never carried from another.
 */
export function forwardCurves(rows: readonly (MarketObsDTO & { hub?: string; tenor?: string })[], hub: string, maxMonths = 18): CurveSnapshot {
  const mine = rows.filter((row) => {
    const rowHub = String(row.hub ?? row.metadata_json?.hub ?? "").toUpperCase();
    const tenor = String(row.tenor ?? row.metadata_json?.tenor ?? "");
    return rowHub === hub.toUpperCase() && MONTH_TENOR.test(tenor);
  });
  const tenorOf = (row: MarketObsDTO & { tenor?: string }) => String(row.tenor ?? row.metadata_json?.tenor ?? "");
  const newest = mine.reduce<string | null>((max, row) => (row.observed_at_utc && (!max || row.observed_at_utc > max) ? row.observed_at_utc : max), null);
  const months = [...new Set(mine.map(tenorOf))].sort().filter((month) => !newest || month >= newest.slice(0, 7)).slice(0, maxMonths);
  const at = (limitIso: string | null) =>
    months.map((month) => {
      const held = mine
        .filter((row) => tenorOf(row) === month && (!limitIso || String(row.observed_at_utc ?? "") <= limitIso))
        .sort((a, b) => String(b.observed_at_utc ?? "").localeCompare(String(a.observed_at_utc ?? "")))[0];
      return held ? inHubUnit(hub, held.price, held.currency, held.unit) : null;
    });
  const shift = (days: number) => (newest ? new Date(Date.parse(newest) - days * 86_400_000).toISOString() : null);
  // A curve "a day ago" is the newest one held at least 20 hours before today's.
  const dayAgo = at(shift(20 / 24));
  const weekAgo = at(shift(7));
  return {
    months,
    today: at(newest),
    dayAgo: dayAgo.some((value) => value !== null) ? dayAgo : months.map(() => null),
    weekAgo: weekAgo.some((value) => value !== null) ? weekAgo : months.map(() => null),
    simulated: mine.length > 0 && mine.every(simulatedRow),
    asOf: newest,
    source: mine[0]?.source_system ?? null,
  };
}

/** Contango (later months dearer) or backwardation, from the first and last month held. */
export function curveShape(values: readonly (number | null)[]): "contango" | "backwardation" | "flat" | null {
  const held = values.filter((value): value is number => value !== null);
  if (held.length < 2) return null;
  const delta = held[held.length - 1]! - held[0]!;
  if (Math.abs(delta) < 1e-9) return "flat";
  return delta > 0 ? "contango" : "backwardation";
}

export interface SpreadHistory {
  days: string[];
  values: number[];
  low: number | null;
  high: number | null;
  rangeDays: number | null;
  transport: number | null;
  simulated: boolean;
  asOf: string | null;
}

/** A spread tenor's last closes (the board's 30), its one-year range and its transport cost,
 * in the unit the board shows it in (`factor` puts EUR/MWh into p/th for an NBP leg). */
export function spreadHistory(tenor: BoardTenorDTO | null | undefined, factor: number | null, transport: number | null): SpreadHistory | null {
  if (!tenor?.available || !tenor.spark || tenor.spark.values.length === 0) return null;
  const scale = (value: number) => (factor !== null ? value * factor : value);
  return {
    days: tenor.spark.days,
    values: tenor.spark.values.map(scale),
    low: tenor.range ? scale(tenor.range.low) : null,
    high: tenor.range ? scale(tenor.range.high) : null,
    rangeDays: tenor.range?.days ?? null,
    transport,
    simulated: Boolean(tenor.simulated),
    asOf: tenor.close_day ?? null,
  };
}
