export const DEFAULT_WORKSPACE_READ_TIMEOUT_MS = 10_000;
export const DEFAULT_LOGOUT_TIMEOUT_MS = 5_000;

export function isIdentityDeniedMessage(message: string): boolean {
  return /^API (401|403)\b/.test(message);
}

/**
 * A 401 means no credential reached the backend, so the session itself is gone.
 * A 403 means the credential is valid but the scope is not, which must not sign
 * an operator out of an otherwise healthy session.
 */
export function isIdentitySessionLostMessage(message: string): boolean {
  return /^API 401\b/.test(message);
}

/** Authentication-first entry vocabulary. */
export type AuthState = "unknown" | "unauthenticated" | "authenticated";

export const UNRESOLVED_AUTH_STATE: AuthState = "unknown";
export const UNAUTHENTICATED_AUTH_STATE: AuthState = "unauthenticated";
export const AUTHENTICATED_AUTH_STATE: AuthState = "authenticated";

/**
 * Identity gate for protected reads. Only a backend-confirmed authenticated
 * session may issue a workspace, market, monitoring or stream request; unknown
 * and unauthenticated both fail closed so nothing can race the identity read.
 */
export function isIdentityGateOpen(authState: AuthState): boolean {
  return authState === AUTHENTICATED_AUTH_STATE;
}

/**
 * True only once identity resolution finished with a denial. `unknown` means the
 * backend is still being asked, so a deep link is left untouched (and unmounted)
 * until the answer arrives.
 */
export function isUnauthenticated(authState: AuthState): boolean {
  return authState === UNAUTHENTICATED_AUTH_STATE;
}

export type WorkspaceEndpointFailureCode = "timeout" | "aborted" | "request";

export interface WorkspaceEndpointFailure {
  code: WorkspaceEndpointFailureCode;
  message: string;
}

export type WorkspaceLoaderOptions = {
  signal?: AbortSignal;
};

export type WorkspaceLoader<T> = (options?: WorkspaceLoaderOptions) => Promise<T>;

export type WorkspaceLoaderOutcome<T> =
  | { ok: true; value: T }
  | { ok: false; error: WorkspaceEndpointFailure };

export interface WorkspaceLoadCommit<T> {
  slices: Record<string, T>;
  endpointErrors: Record<string, string>;
  endpointErrorCodes: Record<string, WorkspaceEndpointFailureCode>;
  loading: false;
  error: string | null;
}

/**
 * Clears every identity-scoped slice and returns the session to the sign-in
 * screen: losing an identity always means "unauthenticated", never "authenticated".
 * Preferences without secrets (theme, language, map tiles, API base URL) are not
 * part of this reset.
 */
export function resetIdentityScopedCaches<T>(monitoringSummary: T) {
  return {
    authState: UNAUTHENTICATED_AUTH_STATE,
    nodes: [],
    edges: [],
    sources: [],
    normalizedMarkets: [],
    marketSpreads: [],
    marketQuotes: [],
    intradayOpportunities: [],
    screenOrders: [],
    pnlSnapshots: [],
    portfolioSummary: null,
    fxRates: [],
    flows: [],
    capacity: [],
    storage: [],
    lng: [],
    tsoAccess: [],
    routes: [],
    routeCandidates: [],
    tsoTariffs: [],
    upstreamContracts: [],
    resourcePoolOptions: null,
    routeRecommendation: null,
    resourcePoolResult: null,
    strategyResult: null,
    strategyRuns: [],
    strategySummary: null,
    reviewDecisions: [],
    reviewMessage: null,
    glossaryTerms: [],
    glossaryContext: null,
    analysisResult: null,
    credentialProviders: [],
    monitoringAlerts: [],
    monitoringSummary,
    monitoringAnalysisByAlert: {},
    monitoringBusyAlertId: null,
    currentUser: null,
    runtimeDb: null,
    runtimeDependencies: null,
    runtimeRelease: null,
    releaseCompatibility: null,
    pipelineHealth: null,
    endpointMeta: {},
    endpointErrors: {},
    endpointErrorCodes: {},
    // Retry bookkeeping belongs to the session that produced the failures.
    endpointRetryBusy: false,
    endpointRetryAttempts: 0,
    endpointRetryLastAttemptAtUtc: null,
    meta: null,
    marketLastUpdatedAtUtc: null,
    loading: false,
    streamingActive: false,
    error: null,
    credentialMessage: null,
    contractSaveMessage: null,
    dataStatus: "unavailable" as const,
  };
}

export interface WorkspaceLoadOptions extends WorkspaceLoaderOptions {
  retries?: number;
  timeoutMs?: number;
}

export async function withAbortTimeout<T>(
  operation: (signal: AbortSignal) => Promise<T>,
  timeoutMs: number,
): Promise<T> {
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Operation timed out after ${timeoutMs}ms.`));
      controller.abort();
    }, timeoutMs);
  });
  try {
    return await Promise.race([operation(controller.signal), timeout]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

/**
 * Message of a failed endpoint read.
 *
 * `String(error)` prefixes an Error with "Error: ", which breaks every consumer
 * that classifies the message by its "API <status>:" prefix - the identity gate
 * reads a 401 as an unreachable backend instead of an anonymous visit. Use the
 * error's own message and fall back to the string form only for non-Errors.
 */
function loadErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

export async function loadWorkspaceEndpoint<T>(
  loader: WorkspaceLoader<T>,
  { signal: parentSignal, retries = 1, timeoutMs = DEFAULT_WORKSPACE_READ_TIMEOUT_MS }: WorkspaceLoadOptions = {},
): Promise<WorkspaceLoaderOutcome<T>> {
  // timeoutMs bounds each attempt; ordinary request failures may still use the retry budget.
  for (let attempt = 0; ; attempt += 1) {
    if (parentSignal?.aborted) {
      return { ok: false, error: { code: "aborted", message: "Workspace load was superseded." } };
    }

    const requestController = new AbortController();
    let timedOut = false;
    const abortRequest = () => requestController.abort();
    parentSignal?.addEventListener("abort", abortRequest, { once: true });
    const timeoutId = setTimeout(() => {
      timedOut = true;
      requestController.abort();
    }, timeoutMs);

    try {
      return { ok: true, value: await loader({ signal: requestController.signal }) };
    } catch (error) {
      if (timedOut) {
        return {
          ok: false,
          error: { code: "timeout", message: `Workspace endpoint timed out after ${timeoutMs}ms.` },
        };
      }
      if (parentSignal?.aborted || isAbortError(error)) {
        return { ok: false, error: { code: "aborted", message: "Workspace load was superseded." } };
      }
      if (attempt >= retries) {
        return { ok: false, error: { code: "request", message: loadErrorMessage(error) } };
      }
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    } finally {
      clearTimeout(timeoutId);
      parentSignal?.removeEventListener("abort", abortRequest);
    }
  }
}

export async function loadWorkspaceEndpoints<T>(
  loaders: ReadonlyArray<readonly [string, WorkspaceLoader<T>]>,
  options: WorkspaceLoadOptions = {},
): Promise<Array<{ key: string; outcome: WorkspaceLoaderOutcome<T> }>> {
  return Promise.all(
    loaders.map(async ([key, loader]) => ({
      key,
      outcome: await loadWorkspaceEndpoint(loader, options),
    })),
  );
}

export function commitWorkspaceLoad<T>(
  outcomes: Array<{ key: string; outcome: WorkspaceLoaderOutcome<T> }>,
): WorkspaceLoadCommit<T> {
  const slices: Record<string, T> = {};
  const endpointErrors: Record<string, string> = {};
  const endpointErrorCodes: Record<string, WorkspaceEndpointFailureCode> = {};
  for (const { key, outcome } of outcomes) {
    if (outcome.ok) {
      slices[key] = outcome.value;
    } else {
      endpointErrors[key] = outcome.error.message;
      endpointErrorCodes[key] = outcome.error.code;
    }
  }
  return {
    slices,
    endpointErrors,
    endpointErrorCodes,
    loading: false,
    error: Object.keys(endpointErrors).length === outcomes.length
      ? `All workspace endpoints failed: ${Object.keys(endpointErrors).join(", ")}`
      : null,
  };
}

export function knownWorkspaceLoaders<T>(
  keys: readonly string[],
  loaders: ReadonlyMap<string, WorkspaceLoader<T>>,
): Array<readonly [string, WorkspaceLoader<T>]> {
  return keys.flatMap((key) => {
    const loader = loaders.get(key);
    return loader ? [[key, loader] as const] : [];
  });
}

export function workspaceLoadHasIdentityDenial<T>(
  outcomes: Array<{ key: string; outcome: WorkspaceLoaderOutcome<T> }>,
): boolean {
  const meOutcome = outcomes.find(({ key }) => key === "me")?.outcome;
  if (meOutcome && !meOutcome.ok && isIdentityDeniedMessage(meOutcome.error.message)) {
    return true;
  }
  // Identity now resolves before any workspace batch, so a 401 inside a batch
  // means the session expired mid-session and the client must fail closed.
  return outcomes.some(
    ({ outcome }) => !outcome.ok && isIdentitySessionLostMessage(outcome.error.message),
  );
}

export function identityDeniedWorkspaceReset<T, S>(
  outcomes: Array<{ key: string; outcome: WorkspaceLoaderOutcome<T> }>,
  monitoringSummary: S,
) {
  return workspaceLoadHasIdentityDenial(outcomes)
    ? resetIdentityScopedCaches(monitoringSummary)
    : null;
}

export class WorkspaceLoadCoordinator {
  private generation = 0;
  private controller: AbortController | null = null;

  start(): { generation: number; signal: AbortSignal } {
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    this.generation += 1;
    return { generation: this.generation, signal: controller.signal };
  }

  isCurrent(generation: number, signal: AbortSignal): boolean {
    return generation === this.generation && !signal.aborted;
  }

  finish(generation: number): void {
    if (generation === this.generation) this.controller = null;
  }

  cancel(): void {
    this.controller?.abort();
    this.controller = null;
    this.generation += 1;
  }
}

export class IdentityReadCoordinator {
  private generation = 0;

  capture(): number {
    return this.generation;
  }

  invalidate(): void {
    this.generation += 1;
  }

  isCurrent(generation: number): boolean {
    return generation === this.generation;
  }
}

export interface ReadRefreshLease {
  signal: AbortSignal;
  release: () => void;
}

export class ReadRefreshLane {
  private activeToken: object | null = null;
  private activeController: AbortController | null = null;

  tryStart(): ReadRefreshLease | null {
    if (this.activeToken) return null;
    const token = {};
    const controller = new AbortController();
    this.activeToken = token;
    this.activeController = controller;
    return {
      signal: controller.signal,
      release: () => {
        if (this.activeToken === token) {
          this.activeToken = null;
          this.activeController = null;
        }
      },
    };
  }

  cancel(): void {
    this.activeController?.abort();
    this.activeController = null;
    this.activeToken = null;
  }
}

export class ReadRefreshCoordinator {
  readonly market = new ReadRefreshLane();
  readonly monitoring = new ReadRefreshLane();
  /**
   * The review lane carries the on-demand ReviewContext read: the review surface asks for
   * its resolved evidence when it opens, and the lane coalesces repeat opens while an
   * identity generation is current.
   */
  readonly review = new ReadRefreshLane();
  private generation = 0;

  beginWorkspaceLoad(): number {
    this.invalidateLanes();
    return this.generation;
  }

  invalidateLanes(): number {
    this.generation += 1;
    this.market.cancel();
    this.monitoring.cancel();
    this.review.cancel();
    return this.generation;
  }

  currentGeneration(): number {
    return this.generation;
  }

  isCurrent(generation: number): boolean {
    return generation === this.generation;
  }
}
