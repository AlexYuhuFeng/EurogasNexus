import {
  normalizeDeliveryProduct,
  normalizeGasDay,
  normalizeHubId,
  type TraderContext,
} from "./traderContext.ts";

export const TRADER_CONTEXT_STORAGE_KEY = "eurogas.traderContext.v1";

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function defaultStorage(): StorageLike | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readPersistedTraderContext(
  storage: StorageLike | null = defaultStorage(),
): Partial<TraderContext> {
  if (!storage) return {};
  let raw: string | null = null;
  try {
    raw = storage.getItem(TRADER_CONTEXT_STORAGE_KEY);
  } catch {
    return {};
  }
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const persisted: Partial<TraderContext> = {};
    const gasDay = normalizeGasDay(typeof parsed.gasDay === "string" ? parsed.gasDay : null);
    if (gasDay) persisted.gasDay = gasDay;
    persisted.deliveryProduct = normalizeDeliveryProduct(
      typeof parsed.deliveryProduct === "string" ? parsed.deliveryProduct : null,
    );
    const hubId = normalizeHubId(typeof parsed.hubId === "string" ? parsed.hubId : null);
    persisted.hubId = hubId;
    return persisted;
  } catch {
    return {};
  }
}

export function writePersistedTraderContext(
  context: TraderContext,
  storage: StorageLike | null = defaultStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(
      TRADER_CONTEXT_STORAGE_KEY,
      JSON.stringify({
        gasDay: context.gasDay,
        deliveryProduct: context.deliveryProduct,
        hubId: context.hubId,
      }),
    );
  } catch {
    // Persistence is best-effort; URL/default precedence remains deterministic.
  }
}
