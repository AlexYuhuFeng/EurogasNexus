import { IDLE_DECISION_ACTION_STATE } from "../app/model/decisionActionModel.ts";

export const DEFAULT_WORKSPACE_READ_TIMEOUT_MS = 10_000;
export const DEFAULT_LOGOUT_TIMEOUT_MS = 5_000;
/**
 * How long the two governed Decision computes wait for an answer.
 *
 * A run holds a per-action pending lane that disables the primary control, so an answer that
 * never arrives must not keep it disabled indefinitely. This is a waiting bound: on expiry the
 * client stops waiting and says so, and the backend may still be computing. Contract saves and
 * logout deliberately keep their own existing bounds.
 */
export const DEFAULT_DECISION_COMPUTE_TIMEOUT_MS = 30_000;

/**
 * The deadline one governed decision compute run is held to: a supplied positive finite bound
 * (the store's tests do), otherwise the named default - never unbounded.
 */
export function decisionComputeTimeoutMs(overrideMs?: number): number {
  return typeof overrideMs === "number" && Number.isFinite(overrideMs) && overrideMs > 0
    ? overrideMs
    : DEFAULT_DECISION_COMPUTE_TIMEOUT_MS;
}

/**
 * A client wait bound expired before its operation answered.
 *
 * The stable code (catalogue name `CLIENT_WAIT_TIMEOUT`) and the taxonomy scalars travel on the
 * error itself, so the existing error presentation classifies it exactly like a backend failure
 * once `errorPresentation.apiErrorBodyFrom` picks these fields up. The message keeps the
 * historical `withAbortTimeout` wording, but no surface renders it.
 */
export class ClientWaitTimeoutError extends Error {
  readonly code = "CLIENT_WAIT_TIMEOUT";
  readonly family = "DEPENDENCY";
  readonly severity = "error";
  readonly recoverability = "retry";
  readonly message_key = "errors.CLIENT_WAIT_TIMEOUT.message";
  readonly action_key = "errors.CLIENT_WAIT_TIMEOUT.action";
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`Operation timed out after ${timeoutMs}ms.`);
    this.name = "ClientWaitTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

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

export type WorkspaceEndpointFailureCode =
  | "timeout"
  | "aborted"
  | "request"
  | "forbidden"
  | "not_found"
  | "server"
  | "network";

/**
 * What a failed read means, from what the request returned: the status panel says "not
 * permitted" or "the server failed", not a blanket "refused" (a timeout or a 500 is not a refusal).
 */
export function requestFailureCode(error: unknown): WorkspaceEndpointFailureCode {
  const status = typeof (error as { status?: unknown })?.status === "number" ? (error as { status: number }).status : null;
  if (status === 401 || status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status !== null && status >= 500) return "server";
  if (status === null || status === 0) return error instanceof TypeError ? "network" : "request";
  return "request";
}

export interface WorkspaceEndpointFailure {
  code: WorkspaceEndpointFailureCode;
  message: string;
}

export type WorkspaceLoaderOptions = {
  signal?: AbortSignal;
  /** Called when the read leaves for the server (api/client.ts read lanes). */
  onDispatch?: () => void;
};

/**
 * How long a workspace read may wait for a read lane before its own bound starts anyway: a loader
 * that does not pass `onDispatch` through is still bounded (by this plus its timeout).
 */
export const WORKSPACE_READ_QUEUE_ALLOWANCE_MS = 20_000;

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
    // The two governed computes' own lifecycle lanes are identity-scoped like the results
    // they label: a refusal or a result provenanced to the closed session must not survive
    // sign-out and be read as the next identity's.
    poolOptimizeAction: IDLE_DECISION_ACTION_STATE,
    routeCompareAction: IDLE_DECISION_ACTION_STATE,
    strategyResult: null,
    strategyRuns: [],
    strategySummary: null,
    reviewDecisions: [],
    reviewMessage: null,
    // The day board's clock is identity-scoped like every other read: the windows one
    // deployment declares and the envelope that said so both leave with the session.
    nominationWindows: [],
    nominationWindowsRead: null,
    nominationWindowsMeta: null,
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
    workspaceLoading: false,
    workspaceLoadsCommitted: 0,
    streamingActive: false,
    error: null,
    credentialMessage: null,
    contractSaveMessage: null,
    contractSaveConflict: false,
    // The reset leaves a new, unread session: nothing has been read about the runtime store yet.
    dataStatus: "unknown" as const,
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
      reject(new ClientWaitTimeoutError(timeoutMs));
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
    // The bound measures the server's answer: it starts when the read leaves for the server
    // (`onDispatch`), not while it waits for a lane behind the page's other reads.
    const expire = () => {
      timedOut = true;
      requestController.abort();
    };
    let timeoutId = setTimeout(expire, timeoutMs + WORKSPACE_READ_QUEUE_ALLOWANCE_MS);
    let dispatched = false;
    const onDispatch = () => {
      if (dispatched) return;
      dispatched = true;
      clearTimeout(timeoutId);
      timeoutId = setTimeout(expire, timeoutMs);
    };

    try {
      return { ok: true, value: await loader({ signal: requestController.signal, onDispatch }) };
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
      const code = requestFailureCode(error);
      // A refusal or a missing route does not change on a second try; a busy server may.
      if (attempt >= retries || code === "forbidden" || code === "not_found") {
        return { ok: false, error: { code, message: loadErrorMessage(error) } };
      }
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs(attempt)));
    } finally {
      clearTimeout(timeoutId);
      parentSignal?.removeEventListener("abort", abortRequest);
    }
  }
}

/**
 * At most this many workspace reads are in flight at once. The batch used to fire about 28 reads
 * together; on a small server they queued behind each other and the last ones passed the 10 s
 * timeout before they started. The order the caller gives is the order they start (the visible
 * task's reads first), and each read's timeout starts when it starts, not while it waits.
 */
export const WORKSPACE_READ_CONCURRENCY = 6;

export async function loadWorkspaceEndpoints<T>(
  loaders: ReadonlyArray<readonly [string, WorkspaceLoader<T>]>,
  options: WorkspaceLoadOptions & { concurrency?: number } = {},
): Promise<Array<{ key: string; outcome: WorkspaceLoaderOutcome<T> }>> {
  const results: Array<{ key: string; outcome: WorkspaceLoaderOutcome<T> }> = new Array(loaders.length);
  let next = 0;
  const width = Math.max(1, Math.min(options.concurrency ?? WORKSPACE_READ_CONCURRENCY, loaders.length));
  const worker = async () => {
    while (next < loaders.length) {
      const index = next;
      next += 1;
      const [key, loader] = loaders[index]!;
      results[index] = { key, outcome: await loadWorkspaceEndpoint(loader, options) };
    }
  };
  await Promise.all(Array.from({ length: width }, worker));
  return results;
}

/** Wait before retry `attempt` (0-based): 400 ms, 800 ms, 1.6 s ..., with a little jitter. */
export function retryDelayMs(attempt: number, random = Math.random): number {
  return Math.round(400 * 2 ** attempt * (0.85 + 0.3 * random()));
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
  /**
   * The day board's lane carries the nomination-windows read: the desk's clock is asked for
   * when the Decision workspace mounts, and the lane coalesces the repeat mounts that every
   * task switch produces instead of re-asking the same question.
   */
  readonly nominationWindows = new ReadRefreshLane();
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
    this.nominationWindows.cancel();
    return this.generation;
  }

  currentGeneration(): number {
    return this.generation;
  }

  isCurrent(generation: number): boolean {
    return generation === this.generation;
  }
}
