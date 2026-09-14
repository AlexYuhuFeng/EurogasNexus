import { useCallback, useEffect, useRef, useState } from "react";
import { useApiStore } from "@/stores/api";
import { isIdentityGateOpen } from "@/stores/workspaceLoading";
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
  traderContextKey,
  type DeliveryProductId,
  type SupportedHubId,
  type TraderContext,
} from "./traderContext.ts";

/**
 * Trader context mirrors what the operator is looking at, so it may only be
 * restored from the URL inside an authenticated session. While identity is
 * unresolved or denied the context resets to defaults and nothing is written
 * back to history.
 */
function contextFromLocation(): TraderContext {
  if (typeof window === "undefined") return DEFAULT_TRADER_CONTEXT;
  if (!isIdentityGateOpen(useApiStore.getState().authState)) return DEFAULT_TRADER_CONTEXT;
  return resolveTraderContext(
    readTraderContextUrl(window.location.search),
    readPersistedTraderContext(),
  );
}

export function useTraderContext() {
  const authState = useApiStore((state) => state.authState);
  const [context, setContext] = useState<TraderContext>(() => contextFromLocation());
  const initialUrlSyncRef = useRef(true);
  const skipNextUrlSyncRef = useRef(false);
  const gateOpen = isIdentityGateOpen(authState);

  useEffect(() => {
    const nextContext = contextFromLocation();
    setContext((current) =>
      traderContextKey(current) === traderContextKey(nextContext) ? current : nextContext,
    );
  }, [authState]);

  useEffect(() => {
    const skipUrlWrite = skipNextUrlSyncRef.current;
    skipNextUrlSyncRef.current = false;
    if (!gateOpen || skipUrlWrite) return;
    writePersistedTraderContext(context);
    const nextUrl = new URL(window.location.href);
    nextUrl.search = traderContextToSearchParams(window.location.search, context);
    if (initialUrlSyncRef.current) {
      window.history.replaceState({ traderContext: context }, "", nextUrl);
      initialUrlSyncRef.current = false;
    } else {
      window.history.pushState({ traderContext: context }, "", nextUrl);
    }
  }, [context, gateOpen]);

  useEffect(() => {
    function syncFromUrl() {
      skipNextUrlSyncRef.current = true;
      setContext(contextFromLocation());
    }
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, [authState]);

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
