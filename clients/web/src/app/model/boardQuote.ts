/**
 * What the hub board reads off a quote (QA-T-01, T-03, T-04), kept apart from the component so
 * it is tested on its own:
 *
 * - **Mid** is (bid + ask) / 2, and only for a two-sided quote. The last trade is never a mid
 *   (it can sit outside the book); a one-sided quote shows its one side, marked as such.
 * - **Change vs close**: the mid against the previous close the server attached to the quote
 *   (the desk's daily closes, else the feed's prior settlement), absolute and in percent.
 * - **Stale**: a quote older than its source's declared cadence (`stale_after_seconds`, as
 *   `/api/sources` reports it), judged on this browser's clock so the age keeps counting
 *   between reads; with no cadence, the server's `freshness_state` decides.
 *
 * Every value here is in the quote's stored basis (per MWh in the quote currency); the board
 * puts it in the hub's own quotation afterwards.
 */
import type { MarketQuoteDTO } from "@/api/client";

type QuoteSides = Pick<MarketQuoteDTO, "bid_price" | "ask_price">;

function finite(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

/** (bid + ask) / 2 when both sides are quoted; otherwise there is no mid. */
export function quoteMid(quote: QuoteSides | null | undefined): number | null {
  if (!quote) return null;
  const bid = finite(quote.bid_price);
  const ask = finite(quote.ask_price);
  return bid !== null && ask !== null ? (bid + ask) / 2 : null;
}

export interface OneSidedQuote {
  side: "bid" | "ask";
  value: number;
}

/** The one side of a quote that has exactly one; null for a two-sided or an empty quote. */
export function quoteOneSided(quote: QuoteSides | null | undefined): OneSidedQuote | null {
  if (!quote) return null;
  const bid = finite(quote.bid_price);
  const ask = finite(quote.ask_price);
  if (bid !== null && ask === null) return { side: "bid", value: bid };
  if (ask !== null && bid === null) return { side: "ask", value: ask };
  return null;
}

export interface QuoteClose {
  price: number;
  /** ISO day of the close; null for a feed's prior settlement, which states no day. */
  day: string | null;
  kind: "settlement" | "close" | "prior_settlement";
  sourceSystem: string | null;
  simulated: boolean;
}

/**
 * The previous close for a hub and tenor: from the newest quote that carries one (a streamed
 * quote arrives without it; the read before it still holds it). Quotes are newest first.
 */
export function quoteClose(history: readonly MarketQuoteDTO[]): QuoteClose | null {
  for (const quote of history) {
    const price = finite(quote.close_price);
    if (price === null || !quote.close_kind) continue;
    return {
      price,
      day: quote.close_day ?? null,
      kind: quote.close_kind,
      sourceSystem: quote.close_source_system ?? null,
      simulated: Boolean(quote.close_simulated),
    };
  }
  return null;
}

export interface ChangeVsClose {
  absolute: number;
  /** Null when the close is zero (no percentage of nothing). */
  percent: number | null;
}

/** The mid's change against the close, in the same basis; null without either. */
export function changeVsClose(mid: number | null, close: number | null): ChangeVsClose | null {
  if (mid === null || close === null || !Number.isFinite(mid) || !Number.isFinite(close)) return null;
  const absolute = mid - close;
  return { absolute, percent: close === 0 ? null : (absolute / Math.abs(close)) * 100 };
}

/** "+0.123 (+0.30 %)": signed both ways, so the direction never rests on colour alone. */
export function formatChangeVsClose(change: ChangeVsClose, decimals = 3): string {
  const sign = (value: number) => (value > 0 ? "+" : value < 0 ? "−" : "");
  const absolute = `${sign(change.absolute)}${Math.abs(change.absolute).toFixed(decimals)}`;
  if (change.percent === null) return absolute;
  return `${absolute} (${sign(change.percent)}${Math.abs(change.percent).toFixed(2)} %)`;
}

/** The source's cadence from the newest quote that states it (quotes newest first). */
export function quoteStaleAfterSeconds(history: readonly MarketQuoteDTO[]): number | null {
  for (const quote of history) {
    const seconds = finite(quote.stale_after_seconds);
    if (seconds !== null && seconds > 0) return seconds;
  }
  return null;
}

/**
 * Whether the quote is stale: older than the source's cadence on this browser's clock; with no
 * cadence known, as the server judged it when it was read.
 */
export function isQuoteStale(
  quote: Pick<MarketQuoteDTO, "freshness_state"> | null | undefined,
  ageSeconds: number | null,
  staleAfterSeconds: number | null,
): boolean {
  if (!quote) return false;
  if (staleAfterSeconds !== null && ageSeconds !== null) return ageSeconds > staleAfterSeconds;
  return String(quote.freshness_state ?? "").toUpperCase() === "STALE";
}

/** A market row's time fields that bound its "Updated" stamp. */
export interface UpdateStampRow {
  observed_at_utc?: string | null;
  received_at_utc?: string | null;
}

function instantMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * QA-R-05: the Prices page's "Updated" stamp. Each row counts at its observed time but never
 * later than the server received it, and the newest is never later than the server's own read
 * (`serverAsOf`): a tick stamped in the future cannot show a time that has not happened yet.
 */
export function latestUpdateStamp(rows: readonly UpdateStampRow[], serverAsOf: string | null = null): string | null {
  let latest: number | null = null;
  for (const row of rows) {
    const observed = instantMs(row.observed_at_utc);
    if (observed === null) continue;
    const received = instantMs(row.received_at_utc);
    const shown = received === null ? observed : Math.min(observed, received);
    latest = latest === null ? shown : Math.max(latest, shown);
  }
  if (latest === null) return null;
  const ceiling = instantMs(serverAsOf);
  return new Date(ceiling === null ? latest : Math.min(latest, ceiling)).toISOString();
}
