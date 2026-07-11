import type { MarketObsDTO } from "@/api/client";

export const DEFAULT_GAS_DAY = new Date().toISOString().slice(0, 10);

export function marketMatchesTradingContext(
  observation: Pick<MarketObsDTO, "product" | "period_start_utc" | "period_end_utc">,
  gasDay: string,
  deliveryProduct: string,
): boolean {
  const gasDayStart = Date.parse(`${gasDay}T00:00:00Z`);
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
