/**
 * Formatting and parsing shared by the limits, delivery and LNG bid panels. Desk units and
 * thousands separators; a missing figure prints as a dash, never as zero.
 */

const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", GBP: "£", USD: "$" };

export function formatMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const magnitude = Math.abs(value);
  const symbol = CURRENCY_SYMBOL[currency] ?? `${currency} `;
  const sign = value < 0 ? "-" : "";
  if (magnitude >= 1_000_000) return `${sign}${symbol}${(magnitude / 1_000_000).toFixed(2)}m`;
  if (magnitude >= 10_000) return `${sign}${symbol}${(magnitude / 1_000).toFixed(0)}k`;
  return `${sign}${symbol}${magnitude.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

export function formatQuantity(value: number | null | undefined, unit = "MWh"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toLocaleString("en-GB", { maximumFractionDigits: 0 })} ${unit}`;
}

/** A price to three decimals with its unit, e.g. "33.125 EUR/MWh". */
export function formatPrice(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toFixed(3)} ${unit}`;
}

/** "a, b  c" -> ["a", "b", "c"]; empties dropped. */
export function splitList(text: string): string[] {
  return text.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
}

/** The next calendar month as "YYYY-MM", the default arrival month for a cargo bid. */
export function nextMonth(today: Date = new Date()): string {
  const year = today.getUTCFullYear() + (today.getUTCMonth() === 11 ? 1 : 0);
  const month = (today.getUTCMonth() + 1) % 12 + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

/** Bar heights for a nominated-vs-allocated strip: fraction of the largest value shown. */
export function deliveryBars(
  days: { nominated_mwh: number | null; allocated_mwh: number | null }[],
): { nominated: number; allocated: number | null }[] {
  const top = Math.max(1, ...days.flatMap((d) => [d.nominated_mwh ?? 0, d.allocated_mwh ?? 0]));
  return days.map((d) => ({
    nominated: (d.nominated_mwh ?? 0) / top,
    allocated: d.allocated_mwh === null ? null : d.allocated_mwh / top,
  }));
}
