import type { MarketObsDTO } from "@/api/client";

export const DEFAULT_GAS_DAY = new Date().toISOString().slice(0, 10);

/**
 * UTC start of the CAM gas day for a calendar date (05:00 CET/CEST):
 * 04:00 UTC in winter, 03:00 UTC while EU DST is active.
 *
 * DST rule (Europe/Berlin): starts on the last Sunday of March at 01:00 UTC,
 * ends on the last Sunday of October at 01:00 UTC. The two transition days
 * themselves are 23/25 hours long; the UI window below uses the +24h
 * approximation on those days only.
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
  const hour = euDstActiveOnUtc(year, month, day) ? 3 : 4;
  return Date.UTC(year, month, day, hour);
}

export function marketMatchesTradingContext(
  observation: Pick<MarketObsDTO, "product" | "period_start_utc" | "period_end_utc">,
  gasDay: string,
  deliveryProduct: string,
): boolean {
  const gasDayStart = gasDayStartUtc(gasDay);
  const gasDayEnd = gasDayStart + 24 * 60 * 60 * 1000;
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
