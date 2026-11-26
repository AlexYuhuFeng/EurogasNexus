/**
 * Inputs a calculation takes from the board by default (UX_REFERENCE rule 25, the live
 * principle): the latest held price for a hub and product, in the unit the calculation asks
 * for, with where it came from. A person may type over it; the result then says so.
 */

export interface BoardObservation {
  hub: string;
  product: string;
  price: number;
  unit: string;
  currency: string;
  price_gbp_mwh?: number | null;
  period_start_utc: string;
  observed_at_utc?: string;
  source_system?: string;
  freshness?: string;
}

export interface BoardPrice {
  value: number;
  /** The gas day or period start it is for ("2026-11-17"). */
  day: string;
  source: string | null;
  simulated: boolean;
}

// Product names carry the hub ("TTF DA", "NBP day-ahead"): match the word, not the whole name.
const PRODUCT_WORDS: Record<"day-ahead" | "within-day", RegExp> = {
  "day-ahead": /\bday-?ahead\b|\bda\b/i,
  "within-day": /\bwithin-?day\b|intraday|\bocm\b|\bwd\b/i,
};

/**
 * The latest price for `hub` and `product` in `currency`/MWh, or, with `quoteUnit`, in the unit
 * the desk quotes the hub in (NBP in p/th) taken as the board holds it, never converted here;
 * null when none is held.
 */
export function latestBoardPrice(
  observations: readonly BoardObservation[],
  hub: string,
  product: "day-ahead" | "within-day",
  currency: string,
  quoteUnit?: string,
): BoardPrice | null {
  const want = PRODUCT_WORDS[product];
  let best: BoardObservation | null = null;
  for (const row of observations) {
    if (row.hub.toUpperCase() !== hub.toUpperCase() || !want.test(row.product.replace(/[_\s]+/g, "-"))) continue;
    if (priceIn(row, currency, quoteUnit) === null) continue;
    if (!best || row.period_start_utc > best.period_start_utc) best = row;
  }
  if (!best) return null;
  return {
    value: priceIn(best, currency, quoteUnit) as number,
    day: best.period_start_utc.slice(0, 10),
    source: best.source_system ?? null,
    simulated: /sim|demo/i.test(best.source_system ?? "") || best.freshness === "simulated",
  };
}

/** The price per MWh in `currency`, from the observation's own unit; null when it is not. */
function priceIn(row: BoardObservation, currency: string, quoteUnit?: string): number | null {
  const unit = row.unit.replace(/\s+/g, "");
  if (quoteUnit) {
    // The board's own quotation, as stored ("p/th" and "GBp/th" are the same unit).
    const same = (text: string) => text.replace(/^p\/th$/i, "GBp/th").toUpperCase();
    return same(unit) === same(quoteUnit) ? row.price : null;
  }
  if (unit.toUpperCase() === `${currency}/MWH`) return row.price;
  // The server's own GBP/MWh normalisation (exact factors, no FX) for an NBP p/th quote.
  if (currency === "GBP" && typeof row.price_gbp_mwh === "number") return row.price_gbp_mwh;
  return null;
}
