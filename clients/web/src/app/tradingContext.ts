import type { MarketObsDTO } from "@/api/client";

export const DEFAULT_GAS_DAY = gasDayLabelForUtc(new Date());

/**
 * UTC start of the CAM gas day for a calendar date (Regulation (EU) 2017/459
 * Article 3(16)): 05:00 UTC in winter and 04:00 UTC while EU DST is active.
 * This is the corrected backend calendar `EU-CAM-UTC-2025`; the legacy
 * `EU-CAM-2025` version is intentionally not used for new computations.
 */
function lastSundayUtc(year: number, monthIndex: number): number {
  for (let day = 31; day >= 25; day -= 1) {
    const candidate = Date.UTC(year, monthIndex, day);
    if (new Date(candidate).getUTCDay() === 0) return candidate;
  }
  return Date.UTC(year, monthIndex, 31);
}

export function euDstActiveOnUtc(year: number, monthIndex: number, day: number): boolean {
  const dstStart = lastSundayUtc(year, 2); // March
  const dstEnd = lastSundayUtc(year, 9); // October
  const instant = Date.UTC(year, monthIndex, day);
  return instant >= dstStart && instant < dstEnd;
}

export function gasDayStartUtc(gasDay: string): number {
  const year = Number(gasDay.slice(0, 4));
  const month = Number(gasDay.slice(5, 7)) - 1;
  const day = Number(gasDay.slice(8, 10));
  const hour = euDstActiveOnUtc(year, month, day) ? 4 : 5;
  return Date.UTC(year, month, day, hour);
}

export function gasDayLabelForUtc(instant: Date = new Date()): string {
  const year = instant.getUTCFullYear();
  const month = instant.getUTCMonth();
  const day = instant.getUTCDate();
  const candidate = new Date(Date.UTC(year, month, day));
  const label = candidate.toISOString().slice(0, 10);
  if (instant.getTime() >= gasDayStartUtc(label)) return label;
  return new Date(Date.UTC(year, month, day - 1)).toISOString().slice(0, 10);
}

export function marketMatchesTradingContext(
  observation: Pick<MarketObsDTO, "product" | "period_start_utc" | "period_end_utc">,
  gasDay: string,
  deliveryProduct: string,
): boolean {
  const gasDayStart = gasDayStartUtc(gasDay);
  const nextDay = new Date(
    Date.UTC(Number(gasDay.slice(0, 4)), Number(gasDay.slice(5, 7)) - 1, Number(gasDay.slice(8, 10)) + 1),
  )
    .toISOString()
    .slice(0, 10);
  const gasDayEnd = gasDayStartUtc(nextDay);
  const periodStart = Date.parse(observation.period_start_utc);
  const periodEnd = Date.parse(observation.period_end_utc);
  const overlapsGasDay = Number.isFinite(periodStart) && Number.isFinite(periodEnd)
    ? periodStart < gasDayEnd && periodEnd > gasDayStart
    : false;
  if (!overlapsGasDay || deliveryProduct === "all") return overlapsGasDay;

  const product = observation.product.toLowerCase().replace(/[_\s]+/g, "-");
  if (deliveryProduct === "day-ahead") return product.includes("day-ahead") || product === "da";
  if (deliveryProduct === "within-day") {
    return product.includes("within-day") || product.includes("intraday") || product.includes("ocm");
  }
  return product.includes("month-ahead") || product.includes("m+1") || product.includes("month-1");
}
