/**
 * Loads the real api store for executable tests.
 *
 * `stores/api.ts` is loaded through the project's own Vite pipeline (TypeScript, the `@` alias)
 * with two modules swapped: `@/api/client`, the HTTP boundary, where each test hands in its own
 * deferred answers, and `zustand`, whose React entry would pull React into a Node process - the
 * vanilla store creator the store actually uses is the same one. Every call gets a fresh module
 * instance, so the module state the store keeps (lanes, generations, a queued re-read) starts
 * where the previous test left it: nowhere.
 */

import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer, type ViteDevServer } from "vite";

import { apiRegistry, type MockApiCall, type MockApiHandler } from "./mockApiClient.ts";

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MOCK_CLIENT = path.join(WEB_ROOT, "tests", "support", "mockApiClient.ts");
const ZUSTAND_VANILLA = path.join(WEB_ROOT, "tests", "support", "zustandVanillaCreate.ts");

/**
 * `@/api/client` reaches the plugin either as written or already expanded by the `@` alias, so both
 * spellings map to the mock. A module path carrying an extension is left alone, which is how a test
 * loads the real client on purpose.
 */
function isMockedClientSpecifier(source: string): boolean {
  const normalized = source.replace(/\\/g, "/").toLowerCase();
  return (
    normalized === "@/api/client" ||
    normalized === path.join(WEB_ROOT, "src", "api", "client").replace(/\\/g, "/").toLowerCase()
  );
}

export interface Deferred<T> {
  readonly promise: Promise<T>;
  readonly resolve: (value: T) => void;
  readonly reject: (error: unknown) => void;
}

/** A promise the test settles itself, for answers that must land at a chosen moment. */
export function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Let the store's own promises and the timers behind them run before the test looks. */
export function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

export interface TradingContextValue {
  gasDay: string;
  deliveryProduct: string;
  hubId: string | null;
}

/** The store surface these tests drive (the real store, typed to what they read). */
export interface ApiStoreState {
  authState: string;
  tradingContext: TradingContextValue;
  marketContext: Record<string, unknown> | null;
  portfolioSnapshot: Record<string, unknown> | null;
  reviewContext: Record<string, unknown> | null;
  screenOrders: unknown[];
  marketQuotes: unknown[];
  reviewDecisions: unknown[];
  endpointMeta: Record<string, unknown>;
  endpointErrors: Record<string, string>;
  endpointErrorCodes: Record<string, string>;
  fetchWorkspace: () => Promise<void>;
  fetchMe: () => Promise<void>;
  subscribeDecisionStreams: () => void;
  refreshMarketData: () => Promise<void>;
  fetchReviewContext: () => Promise<void>;
  retryFailedWorkspaceEndpoints: () => Promise<void>;
  publishTradingContext: (context: TradingContextValue) => void;
  refetchTradingContextProjections: () => Promise<void>;
}

export interface TestApiStore {
  getState: () => ApiStoreState;
  setState: (patch: Partial<ApiStoreState>) => void;
}

export interface ApiStoreHarness {
  readonly store: TestApiStore;
  /** Every endpoint request the store issued, in order. */
  readonly calls: MockApiCall[];
  /** Answer one endpoint; the default for an endpoint nobody answers is an empty envelope. */
  answer(method: string, handler: MockApiHandler): void;
  /** Load one client module through the same pipeline (aliases and TypeScript, nothing mocked). */
  load<T>(modulePath: string): Promise<T>;
}

let serverPromise: Promise<ViteDevServer> | null = null;
let storeLoadCount = 0;

function harnessServer(): Promise<ViteDevServer> {
  serverPromise ??= createServer({
    configFile: false,
    root: WEB_ROOT,
    logLevel: "silent",
    server: { middlewareMode: true },
    appType: "custom",
    resolve: { alias: { "@": path.join(WEB_ROOT, "src") } },
    plugins: [
      {
        name: "eurogas-store-test-modules",
        enforce: "pre",
        resolveId(source: string) {
          if (source === "zustand") return ZUSTAND_VANILLA;
          if (isMockedClientSpecifier(source)) return MOCK_CLIENT;
          return null;
        },
      },
    ],
  });
  return serverPromise;
}

export async function loadApiStore(): Promise<ApiStoreHarness> {
  const vite = await harnessServer();
  const registry = apiRegistry();
  registry.calls.length = 0;
  for (const method of Object.keys(registry.handlers)) delete registry.handlers[method];
  for (const path of Object.keys(registry.streams)) delete registry.streams[path];
  // Identity resolves before any workspace batch, and the batch's own follow-up identity read must
  // find a session: an unexpected 401 would reset the store mid-test. The other two are the batch
  // keys whose slice the store derives from a nested payload, so an unanswered read says "nothing"
  // in the shape those edges expect rather than making the batch throw.
  registry.handlers.me = () => ({
    data: { principal_id: "test-principal", roles: [], permissions: [] },
    meta: {},
  });
  registry.handlers.routeCandidates = () => ({ data: { route_candidates: [] }, meta: {} });
  registry.handlers.tsoTariffs = () => ({ data: { tariffs: [] }, meta: {} });
  // The market lane writes these two slices straight from the envelope, so an unanswered read says
  // "an empty list" rather than handing `null` to code that maps over it.
  registry.handlers.fxRates = () => ({ data: [], meta: {} });
  registry.handlers.sources = () => ({ data: [], meta: {} });
  storeLoadCount += 1;
  const module = (await vite.ssrLoadModule(`/src/stores/api.ts?storeTest=${storeLoadCount}`)) as {
    useApiStore: TestApiStore;
  };
  return {
    store: module.useApiStore,
    calls: registry.calls,
    answer: (method, handler) => {
      registry.handlers[method] = handler;
    },
    load: <T>(modulePath: string) => vite.ssrLoadModule(modulePath) as Promise<T>,
  };
}

/** Release the module pipeline (one dev server, one file watcher, per test process). */
export async function closeApiStoreHarness(): Promise<void> {
  const server = serverPromise;
  serverPromise = null;
  if (server) await (await server).close();
}
