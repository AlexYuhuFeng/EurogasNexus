import { useCallback, useEffect, useRef, useState } from "react";
import { readPersistedTraderContext, writePersistedTraderContext } from "./contextPersistence.ts";
import {
  readTraderContextUrl,
  resolveTraderContext,
  traderContextToSearchParams,
} from "./contextUrl.ts";
import {
  DEFAULT_TRADER_CONTEXT,
  normalizeDeliveryProduct,
  normalizeGasDay,
  normalizeHubId,
  type DeliveryProductId,
  type SupportedHubId,
  type TraderContext,
} from "./traderContext.ts";

function initialTraderContext(): TraderContext {
  if (typeof window === "undefined") return DEFAULT_TRADER_CONTEXT;
  return resolveTraderContext(
    readTraderContextUrl(window.location.search),
    readPersistedTraderContext(),
  );
}

export function useTraderContext() {
  const [context, setContext] = useState<TraderContext>(initialTraderContext);
  const initialUrlSyncRef = useRef(true);
  const skipNextUrlSyncRef = useRef(false);

  useEffect(() => {
    writePersistedTraderContext(context);
    if (skipNextUrlSyncRef.current) {
      skipNextUrlSyncRef.current = false;
      return;
    }
    const nextUrl = new URL(window.location.href);
    nextUrl.search = traderContextToSearchParams(window.location.search, context);
    if (initialUrlSyncRef.current) {
      window.history.replaceState({ traderContext: context }, "", nextUrl);
      initialUrlSyncRef.current = false;
    } else {
      window.history.pushState({ traderContext: context }, "", nextUrl);
    }
  }, [context]);

  useEffect(() => {
    function syncFromUrl() {
      skipNextUrlSyncRef.current = true;
      setContext(
        resolveTraderContext(
          readTraderContextUrl(window.location.search),
          readPersistedTraderContext(),
        ),
      );
    }
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  const setGasDay = useCallback((value: string) => {
    setContext((current) => ({
      ...current,
      gasDay: normalizeGasDay(value, DEFAULT_TRADER_CONTEXT.gasDay),
    }));
  }, []);

  const setDeliveryProduct = useCallback((value: string) => {
    setContext((current) => ({
      ...current,
      deliveryProduct: normalizeDeliveryProduct(value),
    }));
  }, []);

  const setHubId = useCallback((value: string | null) => {
    setContext((current) => ({ ...current, hubId: normalizeHubId(value) }));
  }, []);

  const clearHub = useCallback(() => {
    setContext((current) => ({ ...current, hubId: null }));
  }, []);

  return {
    traderContext: context,
    gasDay: context.gasDay,
    deliveryProduct: context.deliveryProduct,
    hubId: context.hubId,
    setGasDay,
    setDeliveryProduct,
    setHubId,
    clearHub,
  };
}

export type { DeliveryProductId, SupportedHubId, TraderContext };
