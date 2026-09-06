import {
  DEFAULT_TRADER_CONTEXT,
  isDeliveryProductId,
  isGasDayString,
  isSupportedHubId,
  type SupportedHubId,
  type TraderContext,
} from "./traderContext.ts";
import {
  EMPTY_SELECTION_CONTEXT,
  normalizeSelectionId,
  type SelectionContext,
} from "./selectionContext.ts";

export const TRADER_CONTEXT_QUERY_KEYS = {
  gasDay: "gasDay",
  product: "product",
  hub: "hub",
} as const;

export const SELECTION_CONTEXT_QUERY_KEYS = {
  route: "route",
  resource: "resource",
  run: "run",
} as const;

export interface TraderContextUrlValues {
  gasDay?: string | null;
  product?: string | null;
  hub?: string | null;
}

export interface SelectionContextUrlValues {
  route?: string | null;
  resource?: string | null;
  run?: string | null;
}

export function readTraderContextUrl(search: string): TraderContextUrlValues {
  const params = new URLSearchParams(search);
  const values: TraderContextUrlValues = {};
  for (const [field, key] of Object.entries(TRADER_CONTEXT_QUERY_KEYS)) {
    if (params.has(key)) values[field as keyof TraderContextUrlValues] = params.get(key);
  }
  return values;
}

export function readSelectionContextUrl(search: string): SelectionContextUrlValues {
  const params = new URLSearchParams(search);
  const values: SelectionContextUrlValues = {};
  for (const [field, key] of Object.entries(SELECTION_CONTEXT_QUERY_KEYS)) {
    if (params.has(key)) values[field as keyof SelectionContextUrlValues] = params.get(key);
  }
  return values;
}

export function resolveTraderContext(
  urlValues: TraderContextUrlValues,
  persisted: Partial<TraderContext>,
): TraderContext {
  const gasDay =
    urlValues.gasDay !== undefined
      ? isGasDayString(urlValues.gasDay)
        ? urlValues.gasDay
        : DEFAULT_TRADER_CONTEXT.gasDay
      : isGasDayString(persisted.gasDay)
        ? persisted.gasDay
        : DEFAULT_TRADER_CONTEXT.gasDay;

  const deliveryProduct =
    urlValues.product !== undefined
      ? isDeliveryProductId(urlValues.product)
        ? urlValues.product
        : DEFAULT_TRADER_CONTEXT.deliveryProduct
      : isDeliveryProductId(persisted.deliveryProduct)
        ? persisted.deliveryProduct
        : DEFAULT_TRADER_CONTEXT.deliveryProduct;

  let hubId: SupportedHubId | null = null;
  if (urlValues.hub !== undefined) {
    const candidate = urlValues.hub?.trim().toUpperCase() ?? "";
    hubId = isSupportedHubId(candidate) ? candidate : null;
  } else if (persisted.hubId) {
    hubId = isSupportedHubId(persisted.hubId) ? persisted.hubId : null;
  }

  return { gasDay, deliveryProduct, hubId };
}

export function traderContextToSearchParams(
  currentSearch: string,
  context: TraderContext,
): string {
  const next = new URLSearchParams(currentSearch);
  next.set(TRADER_CONTEXT_QUERY_KEYS.gasDay, context.gasDay);
  if (context.deliveryProduct === "all") {
    next.delete(TRADER_CONTEXT_QUERY_KEYS.product);
  } else {
    next.set(TRADER_CONTEXT_QUERY_KEYS.product, context.deliveryProduct);
  }
  if (context.hubId) {
    next.set(TRADER_CONTEXT_QUERY_KEYS.hub, context.hubId);
  } else {
    next.delete(TRADER_CONTEXT_QUERY_KEYS.hub);
  }
  return next.toString();
}

export function resolveSelectionContext(
  urlValues: SelectionContextUrlValues,
): SelectionContext {
  return {
    routeId: urlValues.route !== undefined
      ? normalizeSelectionId(urlValues.route)
      : EMPTY_SELECTION_CONTEXT.routeId,
    resourceId: urlValues.resource !== undefined
      ? normalizeSelectionId(urlValues.resource)
      : EMPTY_SELECTION_CONTEXT.resourceId,
    strategyRunId: urlValues.run !== undefined
      ? normalizeSelectionId(urlValues.run)
      : EMPTY_SELECTION_CONTEXT.strategyRunId,
  };
}

export function selectionContextToSearchParams(
  currentSearch: string,
  context: SelectionContext,
): string {
  const next = new URLSearchParams(currentSearch);
  setOrDelete(next, SELECTION_CONTEXT_QUERY_KEYS.route, context.routeId);
  setOrDelete(next, SELECTION_CONTEXT_QUERY_KEYS.resource, context.resourceId);
  setOrDelete(next, SELECTION_CONTEXT_QUERY_KEYS.run, context.strategyRunId);
  return next.toString();
}

function setOrDelete(
  params: URLSearchParams,
  key: string,
  value: string | null,
): void {
  if (value) params.set(key, value);
  else params.delete(key);
}
