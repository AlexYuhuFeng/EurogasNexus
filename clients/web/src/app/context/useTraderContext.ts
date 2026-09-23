import { useCallback, useEffect, useRef, useState } from "react";
import { useApiStore } from "@/stores/api";
import { isIdentityGateOpen, type AuthState } from "@/stores/workspaceLoading";
import { readPersistedTraderContext, writePersistedTraderContext } from "./contextPersistence.ts";
import { traderContextToSearchParams } from "./contextUrl.ts";
import { resolveSessionTraderContext } from "./sessionTraderContext.ts";
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
function traderContextForSession(authState: AuthState): TraderContext {
  if (typeof window === "undefined") return DEFAULT_TRADER_CONTEXT;
  return resolveSessionTraderContext({
    authState,
    search: window.location.search,
    persisted: readPersistedTraderContext(),
  });
}

export function useTraderContext() {
  const authState = useApiStore((state) => state.authState);
  const publishTradingContext = useApiStore((state) => state.publishTradingContext);
  const [context, setContext] = useState<TraderContext>(() =>
    traderContextForSession(useApiStore.getState().authState),
  );
  const initialUrlSyncRef = useRef(true);
  const skipNextUrlSyncRef = useRef(false);
  const restoredContextRef = useRef<TraderContext | null>(null);
  const gateOpen = isIdentityGateOpen(authState);

  useEffect(() => {
    const nextContext = traderContextForSession(authState);
    restoredContextRef.current = nextContext;
    // Published here, not only through the state update below: the store issues the projections, and
    // on a sign-in the first workspace batch must ask for the context the URL restored rather than
    // the default the previous session left behind. Effects run in hook order, so the store holds
    // the restored context before the runtime's own load effect runs.
    publishTradingContext(nextContext);
    setContext((current) =>
      traderContextKey(current) === traderContextKey(nextContext) ? current : nextContext,
    );
  }, [authState, publishTradingContext]);

  // The store issues every projection read, so the canonical context has to reach it: the owner
  // publishes each resolved context here - including the reset to the default while identity is
  // unresolved or denied - and a changed context supersedes and re-reads the projections this
  // session is showing. The store never restores a context of its own.
  useEffect(() => {
    if (restoredContextRef.current &&
        traderContextKey(context) !== traderContextKey(restoredContextRef.current)) return;
    restoredContextRef.current = null;
    publishTradingContext(context);
  }, [context, publishTradingContext]);

  useEffect(() => {
    const skipUrlWrite = skipNextUrlSyncRef.current;
    skipNextUrlSyncRef.current = false;
    if (!gateOpen || skipUrlWrite) return;
    if (restoredContextRef.current &&
        traderContextKey(context) !== traderContextKey(restoredContextRef.current)) return;
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
      setContext(traderContextForSession(useApiStore.getState().authState));
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
