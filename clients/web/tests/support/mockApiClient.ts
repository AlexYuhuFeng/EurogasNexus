/**
 * The mocked HTTP boundary for executable store tests.
 *
 * `stores/api.ts` imports this module in place of `@/api/client` (see `apiStoreHarness.ts`), so a
 * test hands in the answers it wants and reads back exactly which requests the store issued. No
 * request here reaches a network.
 */

export interface MockApiCall {
  readonly method: string;
  readonly args: unknown[];
}

export type MockApiHandler = (...args: unknown[]) => unknown;

export interface MockApiRegistry {
  readonly calls: MockApiCall[];
  readonly handlers: Record<string, MockApiHandler>;
  readonly streams: Record<string, Record<string, (payload: unknown) => void>>;
}

/**
 * The registry of the running test.
 *
 * It lives on `globalThis` because the store is loaded by Vite's own module runner while the test
 * itself runs in Node: one global is the whole seam between the two.
 */
export function apiRegistry(): MockApiRegistry {
  const global = globalThis as { __eurogasMockApi?: MockApiRegistry };
  global.__eurogasMockApi ??= { calls: [], handlers: {}, streams: {} };
  return global.__eurogasMockApi;
}

/**
 * The endpoint collection the store calls.
 *
 * A method the test did not register answers an empty successful envelope: these tests are about
 * which requests are issued and which answers are written, and an endpoint that only feeds one
 * slice of the batch can answer nothing.
 */
export const api = new Proxy({} as Record<string, (...args: unknown[]) => Promise<unknown>>, {
  get(_target, method: string) {
    return (...args: unknown[]) => {
      const registry = apiRegistry();
      registry.calls.push({ method, args });
      const handler = registry.handlers[method];
      if (!handler) return Promise.resolve({ data: null, meta: {} });
      return Promise.resolve(handler(...args));
    };
  },
});

/** Streams are not opened in these tests; the store only has to be able to close one. */
export function openEventStream(path: string, handlers: Record<string, (payload: unknown) => void>): { close: () => void } {
  apiRegistry().streams[path] = handlers;
  return { close: () => { delete apiRegistry().streams[path]; } };
}

/** Session material belongs to the api client in the product; the store only hands a token over. */
export function setDesktopSessionToken(): void {}
