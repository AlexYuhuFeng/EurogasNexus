import { DEFAULT_GAS_DAY } from "../tradingContext.ts";

export const DELIVERY_PRODUCT_IDS = [
  "all",
  "day-ahead",
  "within-day",
  "month-ahead",
] as const;

export type DeliveryProductId = (typeof DELIVERY_PRODUCT_IDS)[number];

export const SUPPORTED_HUB_IDS = [
  "TTF",
  "NBP",
  "THE",
  "PEG",
  "ZTP",
  "PSV",
] as const;

export type SupportedHubId = (typeof SUPPORTED_HUB_IDS)[number];

export interface TraderContext {
  gasDay: string;
  deliveryProduct: DeliveryProductId;
  hubId: SupportedHubId | null;
}

export const DEFAULT_TRADER_CONTEXT: TraderContext = {
  gasDay: DEFAULT_GAS_DAY,
  deliveryProduct: "all",
  hubId: null,
};

export function isDeliveryProductId(
  value: string | null | undefined,
): value is DeliveryProductId {
  return DELIVERY_PRODUCT_IDS.includes(value as DeliveryProductId);
}

export function normalizeDeliveryProduct(
  value: string | null | undefined,
): DeliveryProductId {
  return isDeliveryProductId(value) ? value : DEFAULT_TRADER_CONTEXT.deliveryProduct;
}

export function isGasDayString(value: string | null | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function normalizeGasDay(
  value: string | null | undefined,
  fallback: string = DEFAULT_TRADER_CONTEXT.gasDay,
): string {
  return isGasDayString(value) ? value : fallback;
}

export function isSupportedHubId(
  value: string | null | undefined,
): value is SupportedHubId {
  return SUPPORTED_HUB_IDS.includes(value as SupportedHubId);
}

export function normalizeHubId(
  value: string | null | undefined,
): SupportedHubId | null {
  if (!value) return null;
  const normalized = value.trim().toUpperCase();
  return isSupportedHubId(normalized) ? normalized : null;
}

export function traderContextKey(context: TraderContext): string {
  return [
    context.gasDay,
    context.deliveryProduct,
    context.hubId ?? "ANY",
  ].join("|");
}
