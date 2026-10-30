import type { MarketQuoteDTO } from "@/api/client";

/**
 * The market ladder: products as rows (nearest delivery first), a Bid Vol | Bid | Offer |
 * Offer Vol group per hub, best bid and best offer across the venues the desk is entitled
 * to (consolidated top of book). This is the layout gas traders read on their execution
 * screens, so it is offered beside the hub board as a familiar view of the same quotes.
 *
 * Values are the stored quotes'; the model only picks the latest quote per venue, then the
 * best price per side, and prefers the screen's native unit (p/th, th/d, MW) when the
 * import kept it, so an NBP row reads in pence per therm as it does on the screen.
 */

export interface LadderSide {
  price: number;
  volume: number | null;
  volumeUnit: string;
  priceUnit: string;
  source: string;
  simulated: boolean;
  observedAtUtc: string;
}

export interface LadderCell {
  bid: LadderSide | null;
  offer: LadderSide | null;
  /** Bid above offer across venues: an arbitrage or a stale quote, flagged not hidden. */
  crossed: boolean;
}

export interface LadderRow {
  key: string;
  label: string;
  /** Prompt products first, as on a trading screen: WD, DA, WE, BOM, then the curve. */
  rank: number;
  deliveryStartUtc: string;
  deliveryEndUtc: string;
  cells: Record<string, LadderCell>;
}

const TENOR_LABELS: Record<string, string> = {
  "within-day": "WD",
  "day-ahead": "DA",
  weekend: "WE",
  "month-ahead": "MA",
};

function metaNumber(quote: MarketQuoteDTO, key: string): number | null {
  const value = quote.metadata_json?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function metaString(quote: MarketQuoteDTO, key: string): string | null {
  const value = quote.metadata_json?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

/** The product label a trader reads: the screen's own label when imported, else WD/DA/WE/MA. */
export function ladderProductLabel(quote: MarketQuoteDTO): string {
  const label = metaString(quote, "product_label");
  const product = quote.product.toLowerCase();
  if (TENOR_LABELS[product]) return TENOR_LABELS[product];
  return label ?? quote.product;
}

function side(quote: MarketQuoteDTO, which: "bid" | "ask"): LadderSide | null {
  const stored = which === "bid" ? quote.bid_price : quote.ask_price;
  if (stored == null || !Number.isFinite(stored)) return null;
  const nativeUnit = metaString(quote, "native_unit");
  const nativePrice = metaNumber(quote, which === "bid" ? "native_bid" : "native_ask");
  const nativeQty = metaNumber(quote, which === "bid" ? "native_bid_qty" : "native_ask_qty");
  const nativeQtyUnit = metaString(quote, "native_quantity_unit");
  const storedQty = which === "bid" ? quote.bid_quantity_mwh : quote.ask_quantity_mwh;
  const useNative = nativeUnit !== null && nativePrice !== null;
  return {
    price: useNative ? nativePrice : stored,
    priceUnit: useNative ? nativeUnit : `${quote.currency}/${quote.unit}`,
    volume: nativeQty ?? (storedQty ?? null),
    volumeUnit: nativeQty !== null && nativeQtyUnit ? nativeQtyUnit : "MWh/d",
    source: quote.source_system,
    simulated: quote.simulated,
    observedAtUtc: quote.observed_at_utc,
  };
}

/** Latest quote per (venue, hub, product), so an old tick never competes with a new one. */
function latestPerVenue(quotes: readonly MarketQuoteDTO[]): MarketQuoteDTO[] {
  const latest = new Map<string, MarketQuoteDTO>();
  for (const quote of quotes) {
    const key = `${quote.source_system}|${quote.hub.toUpperCase()}|${quote.product.toLowerCase()}`;
    const current = latest.get(key);
    if (!current || Date.parse(quote.observed_at_utc) > Date.parse(current.observed_at_utc)) {
      latest.set(key, quote);
    }
  }
  return [...latest.values()];
}

/**
 * Best bid (highest) and best offer (lowest) per hub and product. Sides are compared only
 * within one price unit; a hub quoted in two units keeps the unit of its first best side.
 */
export function buildMarketLadder(quotes: readonly MarketQuoteDTO[], hubs: readonly string[]): LadderRow[] {
  const wanted = new Set(hubs.map((hub) => hub.toUpperCase()));
  const latest = latestPerVenue(quotes).filter((quote) => wanted.has(quote.hub.toUpperCase()));
  // Real quotes and simulated ones never compete for best price: where a real quote exists
  // for a hub and delivery window, simulated quotes for it are dropped.
  const realWindows = new Set(
    latest.filter((quote) => !quote.simulated).map((quote) => `${quote.hub.toUpperCase()}|${windowKey(quote)}`),
  );
  const rows = new Map<string, LadderRow>();
  for (const quote of latest) {
    const hub = quote.hub.toUpperCase();
    const key = windowKey(quote);
    if (quote.simulated && realWindows.has(`${hub}|${key}`)) continue;
    // One row per delivery window: a "month-ahead" quote and a "Nov-26" quote for the same
    // month are the same instrument, labelled with the screen's own name when one exists.
    const label = ladderProductLabel(quote);
    const row = rows.get(key) ?? {
      key,
      label,
      rank: promptRank(quote),
      deliveryStartUtc: quote.delivery_start_utc,
      deliveryEndUtc: quote.delivery_end_utc,
      cells: {},
    };
    if (row.label === "MA" && label !== "MA") row.label = label;
    const cell = row.cells[hub] ?? { bid: null, offer: null, crossed: false };
    const bid = side(quote, "bid");
    const offer = side(quote, "ask");
    if (bid && (!cell.bid || (bid.priceUnit === cell.bid.priceUnit && bid.price > cell.bid.price))) {
      cell.bid = bid;
    }
    if (offer && (!cell.offer || (offer.priceUnit === cell.offer.priceUnit && offer.price < cell.offer.price))) {
      cell.offer = offer;
    }
    cell.crossed = Boolean(
      cell.bid && cell.offer && cell.bid.priceUnit === cell.offer.priceUnit && cell.bid.price > cell.offer.price,
    );
    row.cells[hub] = cell;
    rows.set(key, row);
  }
  // Prompt products first; then nearest delivery, and for the same start the shorter product
  // first (Jan-27, Q1-27, Cal-27).
  return [...rows.values()].sort((left, right) => {
    if (left.rank !== right.rank) return left.rank - right.rank;
    const delta = Date.parse(left.deliveryStartUtc) - Date.parse(right.deliveryStartUtc);
    if (delta !== 0) return delta;
    return Date.parse(left.deliveryEndUtc) - Date.parse(right.deliveryEndUtc);
  });
}

const PROMPT_RANK: Record<string, number> = {
  "within-day": 0,
  within_day: 0,
  "day-ahead": 1,
  day_ahead: 1,
  weekend: 2,
  balance_of_month: 3,
};

function promptRank(quote: MarketQuoteDTO): number {
  const kind = metaString(quote, "product_kind") ?? quote.product.toLowerCase();
  return PROMPT_RANK[kind] ?? PROMPT_RANK[quote.product.toLowerCase()] ?? 4;
}

function windowKey(quote: MarketQuoteDTO): string {
  return `${Date.parse(quote.delivery_start_utc)}|${Date.parse(quote.delivery_end_utc)}`;
}

export function formatLadderPrice(sideValue: LadderSide | null): string {
  if (!sideValue) return "";
  return sideValue.price.toFixed(sideValue.priceUnit === "GBp/th" ? 2 : 3);
}

export function formatLadderVolume(sideValue: LadderSide | null): string {
  if (!sideValue || sideValue.volume === null) return "";
  return Math.round(sideValue.volume).toLocaleString("en-GB");
}

export const LADDER_DEFAULT_HUBS = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV"];
