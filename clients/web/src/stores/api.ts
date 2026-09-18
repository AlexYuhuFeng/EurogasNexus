import { create } from "zustand";
import {
  CLIENT_RELEASE_METADATA,
  ReleaseCompatibility,
  compatibilityForServer,
} from "@/app/releaseCompatibility";
import {
  HOST_COMMANDS,
  isDesktopHost,
  requireHostCommand,
} from "@/app/host/hostCapabilities";
import {
  contextAlerts,
  contextIsUsable,
  contextNormalizedRows,
  contextOpportunities,
  contextQuotes,
  sliceRows,
} from "@/app/model/marketContextModel";
import {
  snapshotIsUsable,
  snapshotPnlSnapshots,
  snapshotResourcePoolOptions,
  snapshotScreenOrders,
  snapshotSummary,
} from "@/app/model/portfolioSnapshotModel";
import { reviewDecisions, reviewIsUsable } from "@/app/model/reviewContextModel";
import {
  analysisSnapshotReadiness,
  analysisSnapshotRequest,
  snapshotContextFrom,
} from "@/app/model/analysisSnapshotModel";
import { sourceRunOutcome, type SourceRunOutcome } from "@/app/model/sourceRunModel";
import {
  api,
  AnalysisRequestDTO,
  AnalysisResultDTO,
  AnalysisSnapshotDTO,
  ApiMeta,
  CapacityObsDTO,
  CredentialProviderDTO,
  CurrentUserDTO,
  EdgeDTO,
  FlowObsDTO,
  FxRateDTO,
  GlossaryTermDTO,
  JobDTO,
  DataProductCatalogueDTO,
  AgentRunDTO,
  GlossaryContextDTO,
  LngObsDTO,
  IntradayOpportunityDTO,
  MarketContextProjectionDTO,
  MarketQuoteDTO,
  MarketSpreadDTO,
  MonitoringAlertDTO,
  MonitoringAnalysisDTO,
  MonitoringSummaryDTO,
  NodeDTO,
  NormalizedMarketObsDTO,
  PipelineHealthDTO,
  PortfolioLiveSummaryDTO,
  PortfolioOptimizationRequestDTO,
  PortfolioOptimizationResultDTO,
  PortfolioPnlSnapshotDTO,
  PortfolioSnapshotProjectionDTO,
  ResourcePoolOptionsDTO,
  ReviewContextProjectionDTO,
  ReviewDecisionDTO,
  ReviewDecisionInputDTO,
  RouteRecommendationRequestDTO,
  RouteRecommendationResultDTO,
  RouteCandidateDTO,
  RouteEligibilityDTO,
  RuntimeDbStatusDTO,
  RuntimeDependenciesDTO,
  RuntimeReleaseDTO,
  ScreenOrderObservationDTO,
  SourceSystemDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StrategyRunDTO,
  StrategySummaryDTO,
  StorageObsDTO,
  TsoAccessPointDTO,
  TsoTariffDTO,
  UpstreamContractDTO,
  UpstreamContractInputDTO,
  openEventStream,
} from "@/api/client";
import {
  DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
  DEFAULT_LOGOUT_TIMEOUT_MS,
  AUTHENTICATED_AUTH_STATE,
  commitWorkspaceLoad,
  identityDeniedWorkspaceReset,
  isIdentityGateOpen,
  loadWorkspaceEndpoint,
  loadWorkspaceEndpoints,
  knownWorkspaceLoaders,
  IdentityReadCoordinator,
  ReadRefreshCoordinator,
  resetIdentityScopedCaches,
  isIdentityDeniedMessage,
  UNRESOLVED_AUTH_STATE,
  UNAUTHENTICATED_AUTH_STATE,
  withAbortTimeout,
  WorkspaceEndpointFailureCode,
  type AuthState,
  type WorkspaceLoaderOutcome,
  WorkspaceLoadCoordinator,
  type WorkspaceLoader,
} from "./workspaceLoading";
import {
  SESSION_EXPIRED_KEY,
  UNKNOWN_AUTH_STATUS,
  authStatusSnapshot,
  bootstrapStartState,
  devLoginCurrentUser,
  devLoginErrorKey,
  identityFailureKey,
  oidcSignInErrorKey,
  resolveIdentity,
  type AuthStatusSnapshot,
} from "./authGate";

let decisionStreamClosers: Array<() => void> = [];
let marketRefreshSequence = 0;
const workspaceLoadCoordinator = new WorkspaceLoadCoordinator();
const readRefreshCoordinator = new ReadRefreshCoordinator();
const identityReadCoordinator = new IdentityReadCoordinator();
const MARKET_REFRESH_ERROR_PREFIX = "Market refresh partial:";
/** How many recent Analysis Snapshots the reproducibility picker offers. */
const SNAPSHOT_PICKER_LIMIT = 25;
let logoutInProgress = false;

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function latestTimestamp(values: Array<string | null | undefined>): string | null {
  const latestTimestampMs = values.reduce<number>(
    (latest, value) => Math.max(latest, value ? timestampMs(value) : 0),
    0,
  );
  return latestTimestampMs > 0 ? new Date(latestTimestampMs).toISOString() : null;
}

function closeDecisionStreams() {
  decisionStreamClosers.forEach((close) => close());
  decisionStreamClosers = [];
}

function startWorkspaceLoad() {
  readRefreshCoordinator.beginWorkspaceLoad();
  return workspaceLoadCoordinator.start();
}

function invalidateIdentitySession() {
  identityReadCoordinator.invalidate();
  readRefreshCoordinator.invalidateLanes();
  workspaceLoadCoordinator.cancel();
  closeDecisionStreams();
}

function isIdentityDenied(error: unknown): boolean {
  return error instanceof Error && isIdentityDeniedMessage(error.message);
}

/**
 * User-triggered follow-up reads answer a question asked by one identity, so a
 * response may only be written back while that identity is still the current
 * one. A sign-out or a sign-in as another principal invalidates the generation;
 * a late response from the previous generation is dropped rather than written
 * into a shell that no longer represents it.
 */
function followUpReadIsCurrent(generation: number): boolean {
  return !logoutInProgress && identityReadCoordinator.isCurrent(generation);
}

function mergeMarketQuotes(
  current: MarketQuoteDTO[],
  incoming: MarketQuoteDTO[],
): MarketQuoteDTO[] {
  const byId = new Map(current.map((quote) => [quote.quote_id, quote]));
  incoming.forEach((quote) => {
    const existing = byId.get(quote.quote_id);
    if (!existing || timestampMs(quote.observed_at_utc) >= timestampMs(existing.observed_at_utc)) {
      byId.set(quote.quote_id, quote);
    }
  });
  return Array.from(byId.values())
    .sort((left, right) => timestampMs(right.observed_at_utc) - timestampMs(left.observed_at_utc))
    .slice(0, 500);
}

function mergeIntradayOpportunities(
  current: IntradayOpportunityDTO[],
  incoming: IntradayOpportunityDTO[],
): IntradayOpportunityDTO[] {
  const byId = new Map(current.map((item) => [item.opportunity_id, item]));
  incoming.forEach((item) => {
    const existing = byId.get(item.opportunity_id);
    if (!existing || timestampMs(item.detected_at_utc) >= timestampMs(existing.detected_at_utc)) {
      byId.set(item.opportunity_id, item);
    }
  });
  return Array.from(byId.values())
    .sort((left, right) => timestampMs(right.detected_at_utc) - timestampMs(left.detected_at_utc))
    .slice(0, 100);
}

function latestMarketObservedAt(
  normalizedMarkets: NormalizedMarketObsDTO[],
  marketQuotes: MarketQuoteDTO[],
  fxRates: FxRateDTO[],
): string | null {
  const timestamps = [
    ...normalizedMarkets.map((row) => row.observed_at_utc),
    ...marketQuotes.map((row) => row.observed_at_utc),
    ...fxRates.map((row) => row.observed_at_utc),
  ].filter((value): value is string => Boolean(value));
  return latestTimestamp(timestamps);
}

/**
 * Architecture V2 Wave 5: map one market-context projection onto the market lane.
 *
 * The projection is the market surface's coherent source - one as-of instant, one
 * time basis, per-slice freshness. Its slices are written into the same state
 * fields the surfaces already read, so no downstream model changes, while every
 * value now comes from a single payload.
 *
 * The projection is never treated as an empty market: a payload the backend could
 * not serve (or whose quotes slice was withheld) leaves the previous values in
 * place, and the surface qualifies them from `sliceReadings`/`degradedSlices`.
 */
function applyMarketContext(
  state: ApiState,
  projection: MarketContextProjectionDTO | null,
  fxRates: FxRateDTO[] = state.fxRates,
): Pick<
  ApiState,
  | "marketContext"
  | "normalizedMarkets"
  | "marketSpreads"
  | "marketQuotes"
  | "intradayOpportunities"
  | "monitoringAlerts"
  | "marketLastUpdatedAtUtc"
> {
  const usable = contextIsUsable(projection);
  const normalizedMarkets = usable ? contextNormalizedRows(projection) : state.normalizedMarkets;
  const marketSpreads = usable
    ? sliceRows<MarketSpreadDTO>(projection, "spreads")
    : state.marketSpreads;
  const marketQuotes = usable
    ? mergeMarketQuotes(state.marketQuotes, contextQuotes(projection))
    : state.marketQuotes;
  const intradayOpportunities = usable
    ? mergeIntradayOpportunities(state.intradayOpportunities, contextOpportunities(projection))
    : state.intradayOpportunities;
  const monitoringAlerts = usable ? contextAlerts(projection) : state.monitoringAlerts;

  return {
    marketContext: projection,
    normalizedMarkets,
    marketSpreads,
    marketQuotes,
    intradayOpportunities,
    monitoringAlerts,
    marketLastUpdatedAtUtc: latestMarketObservedAt(normalizedMarkets, marketQuotes, fxRates),
  };
}

/**
 * Architecture V2 Wave 5: map one portfolio-snapshot projection onto the portfolio
 * lane. The projection's slices fill the same ApiState fields the surfaces already
 * read, so no downstream model changes.
 *
 * The summary is an aggregate: a projection whose summary slice the backend did not
 * serve leaves the previous values in place instead of reporting an unmeasured
 * portfolio as an empty (zero-valued) one.
 */
function applyPortfolioSnapshot(
  state: ApiState,
  projection: PortfolioSnapshotProjectionDTO | null,
): Pick<
  ApiState,
  | "portfolioSnapshot"
  | "screenOrders"
  | "pnlSnapshots"
  | "portfolioSummary"
  | "resourcePoolOptions"
> {
  if (!snapshotIsUsable(projection)) {
    return {
      portfolioSnapshot: projection,
      screenOrders: state.screenOrders,
      pnlSnapshots: state.pnlSnapshots,
      portfolioSummary: state.portfolioSummary,
      resourcePoolOptions: state.resourcePoolOptions,
    };
  }
  return {
    portfolioSnapshot: projection,
    screenOrders: snapshotScreenOrders(projection),
    pnlSnapshots: snapshotPnlSnapshots(projection),
    portfolioSummary: snapshotSummary(projection),
    // The pool block comes from the same coherent payload instead of a second route
    // call, and a slice the backend withheld leaves the previous options in place.
    resourcePoolOptions: snapshotResourcePoolOptions(projection) ?? state.resourcePoolOptions,
  };
}

/**
 * Projection lanes read through one loader key but write several state fields.
 * A retried projection must re-derive every field it feeds, so the retry path maps
 * the payload through the same applier the periodic lane uses.
 */
const PROJECTION_LANE_APPLIERS: Record<
  string,
  (state: ApiState, payload: unknown) => Partial<ApiState>
> = {
  marketContext: (state, payload) =>
    applyMarketContext(state, payload as MarketContextProjectionDTO | null),
  portfolioSnapshot: (state, payload) =>
    applyPortfolioSnapshot(state, payload as PortfolioSnapshotProjectionDTO | null),
  reviewContext: (state, payload) => {
    const projection = payload as ReviewContextProjectionDTO | null;
    return {
      reviewContext: projection,
      reviewDecisions: reviewIsUsable(projection)
        ? reviewDecisions(projection)
        : state.reviewDecisions,
    };
  },
};

export interface ApiState {
  authState: AuthState;
  authStatus: AuthStatusSnapshot;
  /** i18n key of the last authentication failure, localised by the sign-in screen. */
  authErrorKey: string | null;
  authNoticeKey: string | null;
  authBusy: boolean;
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  sources: SourceSystemDTO[];
  normalizedMarkets: NormalizedMarketObsDTO[];
  marketSpreads: MarketSpreadDTO[];
  marketQuotes: MarketQuoteDTO[];
  intradayOpportunities: IntradayOpportunityDTO[];
  marketContext: MarketContextProjectionDTO | null;
  portfolioSnapshot: PortfolioSnapshotProjectionDTO | null;
  reviewContext: ReviewContextProjectionDTO | null;
  screenOrders: ScreenOrderObservationDTO[];
  pnlSnapshots: PortfolioPnlSnapshotDTO[];
  portfolioSummary: PortfolioLiveSummaryDTO | null;
  fxRates: FxRateDTO[];
  flows: FlowObsDTO[];
  capacity: CapacityObsDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  tsoAccess: TsoAccessPointDTO[];
  routes: RouteEligibilityDTO[];
  routeCandidates: RouteCandidateDTO[];
  tsoTariffs: TsoTariffDTO[];
  upstreamContracts: UpstreamContractDTO[];
  resourcePoolOptions: ResourcePoolOptionsDTO | null;
  routeRecommendation: RouteRecommendationResultDTO | null;
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  strategyResult: StrategyLabResultDTO | null;
  strategyRuns: StrategyRunDTO[];
  strategySummary: StrategySummaryDTO | null;
  reviewDecisions: ReviewDecisionDTO[];
  reviewMessage: string | null;
  glossaryTerms: GlossaryTermDTO[];
  glossaryContext: GlossaryContextDTO | null;
  analysisResult: AnalysisResultDTO | null;
  credentialProviders: CredentialProviderDTO[];
  monitoringAlerts: MonitoringAlertDTO[];
  monitoringSummary: MonitoringSummaryDTO;
  monitoringAnalysisByAlert: Record<string, MonitoringAnalysisDTO>;
  monitoringBusyAlertId: string | null;
  currentUser: CurrentUserDTO | null;
  runtimeDb: RuntimeDbStatusDTO | null;
  runtimeDependencies: RuntimeDependenciesDTO | null;
  runtimeRelease: RuntimeReleaseDTO | null;
  releaseCompatibility: ReleaseCompatibility | null;
  pipelineHealth: PipelineHealthDTO | null;
  endpointMeta: Record<string, ApiMeta>;
  endpointErrors: Record<string, string>;
  endpointErrorCodes: Record<string, WorkspaceEndpointFailureCode>;
  /** True while a failed-endpoint retry pass is in flight: one attempt at a time. */
  endpointRetryBusy: boolean;
  /** Bounded retry attempts started in this session, surfaced by the banner. */
  endpointRetryAttempts: number;
  /** Start time (UTC ISO) of the last retry attempt, or null before the first. */
  endpointRetryLastAttemptAtUtc: string | null;
  meta: ApiMeta | null;
  /**
   * Recent Analysis Snapshots (Architecture V2 Wave 4), read when the review task opens.
   *
   * The list is the deployment's own record of reproducibility references, so a surface may
   * offer a choice among them but never invent one. `analysisSnapshotSource` records what the
   * backend cited as the read's origin, so an empty list caused by a deployment without a
   * runtime database is not read as "nothing was ever recorded".
   */
  analysisSnapshots: AnalysisSnapshotDTO[];
  analysisSnapshotSource: string | null;
  /** `recorded` after a snapshot was written and read back; null otherwise. */
  snapshotMessage: string | null;
  /** The reproducibility reference the next report run cites, or null for none. */
  reviewSnapshotId: string | null;
  marketLastUpdatedAtUtc: string | null;
  loading: boolean;
  streamingActive: boolean;
  error: string | null;
  credentialMessage: string | null;
  contractSaveMessage: string | null;
  /** The last queued ingestion run, as the source surface shows it. */
  sourceRunOutcome: SourceRunOutcome | null;
  /**
   * The most recent jobs the activity timeline read.
   *
   * The timeline owns that read (it is a bounded, operator-triggered refresh rather than a
   * workspace loader), but the Inspector resolves detail from state the identity already received,
   * so the rows it fetched are published here for the `job` subject to resolve against. Nothing
   * else reads them.
   */
  jobs: JobDTO[];
  publishJobsRead: (jobs: JobDTO[]) => void;
  /**
   * The Data Product catalogue the research surface read (Architecture V2 Wave 4).
   *
   * The catalogue panel owns that read - it is a bounded, on-demand read rather than a workspace
   * loader - but the Inspector resolves detail from state the identity already received, so the
   * entries it fetched are published here for the `data-product` subject. Nothing else reads them.
   */
  dataProducts: DataProductCatalogueDTO | null;
  publishDataProductsRead: (catalogue: DataProductCatalogueDTO | null) => void;
  /**
   * The agent runs the research surface read, for the `agent-run` subject.
   *
   * Same pattern as the jobs and catalogue reads: the surface owns the read, and the Inspector
   * resolves detail from what the identity already received rather than fetching.
   */
  agentRuns: AgentRunDTO[];
  publishAgentRunsRead: (runs: AgentRunDTO[]) => void;
  /**
   * Queue one manual ingestion run for a source.
   *
   * The route queues it for the dataops worker; nothing executes inside the request. A refusal
   * (unknown source, no runtime store) is reported as itself and leaves no outcome behind, so the
   * surface cannot show a run that was never queued.
   */
  requestSourceRun: (sourceId: string, reason: string) => Promise<void>;
  dataStatus: "runtime" | "delayed" | "partial" | "unavailable";
  bootstrapIdentity: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  fetchWorkspace: () => Promise<void>;
  retryFailedWorkspaceEndpoints: () => Promise<void>;
  refreshMarketData: () => Promise<void>;
  subscribeDecisionStreams: () => void;
  refreshMonitoring: () => Promise<void>;
  /**
   * Read the review projection (decisions, resolved evidence, monitoring posture) on
   * demand. The review surface calls this when it opens; it is never part of the
   * workspace batch, because resolving evidence is per-entity work.
   */
  fetchReviewContext: () => Promise<void>;
  fetchAnalysisSnapshots: () => Promise<void>;
  /**
   * Record the context the caller is standing in as a reproducibility reference, and select it.
   *
   * Returns the message key the surface should show, or null when nothing was recorded. The
   * list is re-read from the backend afterwards rather than appended to optimistically, and the
   * recorded reference becomes the citation the next report run carries - that is the order the
   * workflow has: freeze the context, then cite it.
   */
  recordAnalysisSnapshot: (
    context: Record<string, string | null | undefined>,
    runtimeDbReady: boolean,
  ) => Promise<string | null>;
  setReviewSnapshotId: (snapshotId: string | null) => void;
  fetchMe: () => Promise<void>;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  saveProviderCredential: (providerId: string, apiKey: string, label: string) => Promise<void>;
  testProviderConnection: (providerId: string) => Promise<void>;
  acknowledgeMonitoringAlert: (alertId: string) => Promise<void>;
  analyzeMonitoringAlert: (
    alertId: string,
    question: string,
    language: "en" | "zh-CN",
  ) => Promise<void>;
  saveDraftContract: (contract: UpstreamContractInputDTO) => Promise<void>;
  recordReviewDecision: (body: ReviewDecisionInputDTO) => Promise<void>;
  recommendRouteAllocation: (request: RouteRecommendationRequestDTO) => Promise<void>;
  optimizeResourcePool: (request: PortfolioOptimizationRequestDTO) => Promise<void>;
  evaluateStrategyLab: (scenario: StrategyLabRequestDTO) => Promise<void>;
  fetchStrategySummary: () => Promise<void>;
  fetchStrategyRuns: () => Promise<void>;
  fetchGlossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) => Promise<void>;
  askAnalysis: (body: AnalysisRequestDTO) => Promise<void>;
  generatePortfolioReport: (body: AnalysisRequestDTO) => Promise<void>;
}



function generatePkceVerifier(): string {
  const bytes = new Uint8Array(48);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

async function generatePkceChallenge(verifier: string): Promise<string> {
  const bytes = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return base64Url(new Uint8Array(digest));
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((value) => { binary += String.fromCharCode(value); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const DEFAULT_STRATEGY_ID = "nbp-sap-icis-ocm-window";

function withoutLegacyFlag<T extends object>(body: T): T {
  const payload = { ...body } as Record<string, unknown>;
  delete payload["research" + "_only"];
  return payload as T;
}

// ---------------------------------------------------------------------------
// Independent endpoint loading. Each endpoint has its own deadline and retry;
// failures are recorded per endpoint and can be retried without reloading the workspace.
// ---------------------------------------------------------------------------

type LoaderOutcome<T> = { ok: true; value: T } | { ok: false; error: string };

async function loadEndpointWithRetry<T>(
  loader: () => Promise<T>,
  retries = 1,
): Promise<LoaderOutcome<T>> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return { ok: true, value: await loader() };
    } catch (error) {
      if (attempt >= retries) return { ok: false, error: String(error) };
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
}

/**
 * endpointMeta key -> loader. Keys keep the historical endpointMeta names.
 * Identity (`/me`) is deliberately NOT part of this batch: it is resolved by
 * `bootstrapIdentity()` before any protected endpoint may be requested.
 */
type WorkspaceResponse = { data: unknown; meta: ApiMeta };
type WorkspaceApiLoader = WorkspaceLoader<WorkspaceResponse>;
const WORKSPACE_LOADERS: Array<[string, WorkspaceApiLoader]> = [
  ["referenceNodes", (options) => api.nodes(undefined, options)],
  ["referenceEdges", (options) => api.edges(undefined, options)],
  ["sources", api.sources],
  ["normalizedMarkets", api.normalizedMarketObservations],
  ["marketSpreads", api.marketSpreads],
  ["marketQuotes", api.marketQuotes],
  ["intradayOpportunities", api.intradayOpportunities],
  // Architecture V2 Wave 5: the portfolio lane reads ONE coherent projection
  // (summary, screen orders, PnL snapshots, contracts on one as-of) instead of
  // joining /portfolio/live-summary, /portfolio/screen-orders and
  // /portfolio/pnl-snapshots. The slices fill the same ApiState fields.
  ["portfolioSnapshot", (options) => api.portfolioSnapshot(undefined, options)],
  ["fxRates", api.fxRates],
  ["flows", api.flowObservations],
  ["capacity", api.capacityObservations],
  ["storage", api.storageObservations],
  ["lng", api.lngObservations],
  ["tsoAccess", (options) => api.tsoAccess(undefined, options)],
  ["routes", api.routeEligibility],
  ["routeCandidates", api.routeCandidates],
  ["tsoTariffs", api.tsoTariffs],
  ["upstreamContracts", api.upstreamContracts],
  ["glossaryTerms", (options) => api.glossary("en", undefined, options)],
  ["runtimeDb", api.runtimeDb],
  ["runtimeDependencies", api.runtimeDependencies],
  ["credentialProviders", api.credentialProviders],
  ["monitoringAlerts", api.monitoringAlerts],
  ["monitoringSummary", api.monitoringSummary],
  ["reviewDecisions", (options) => api.reviewDecisions(undefined, options)],
  ["pipelineHealth", api.pipelineHealth],
];

/**
 * Retry-only loaders: reads the market lane performs outside the workspace batch.
 *
 * They are deliberately absent from WORKSPACE_LOADERS so an initial workspace load
 * does not request the projection a second time, but a failed market read stays
 * retryable through the same bounded control as every other endpoint.
 */
const RETRY_ONLY_LOADERS: Array<[string, WorkspaceApiLoader]> = [
  ["marketContext", (options) => api.marketContext(undefined, options)],
  ["reviewContext", (options) => api.reviewContext(undefined, options)],
];

/** endpointMeta key -> ApiState slice key. */
const WORKSPACE_STATE_KEYS: Record<string, keyof ApiState> = {
  referenceNodes: "nodes",
  referenceEdges: "edges",
  sources: "sources",
  normalizedMarkets: "normalizedMarkets",
  marketSpreads: "marketSpreads",
  marketQuotes: "marketQuotes",
  intradayOpportunities: "intradayOpportunities",
  fxRates: "fxRates",
  flows: "flows",
  capacity: "capacity",
  storage: "storage",
  lng: "lng",
  tsoAccess: "tsoAccess",
  routes: "routes",
  routeCandidates: "routeCandidates",
  tsoTariffs: "tsoTariffs",
  upstreamContracts: "upstreamContracts",
  glossaryTerms: "glossaryTerms",
  runtimeDb: "runtimeDb",
  runtimeDependencies: "runtimeDependencies",
  credentialProviders: "credentialProviders",
  monitoringAlerts: "monitoringAlerts",
  monitoringSummary: "monitoringSummary",
  reviewDecisions: "reviewDecisions",
  pipelineHealth: "pipelineHealth",
};

function deriveWorkspaceSlice(key: string, response: { data: unknown }): unknown {
  if (key === "routeCandidates") {
    return (response.data as { route_candidates: unknown }).route_candidates;
  }
  if (key === "tsoTariffs") {
    return (response.data as { tariffs: unknown }).tariffs;
  }
  return response.data;
}

const DEFAULT_MONITORING_SUMMARY = {
  open_count: 0,
  acknowledged_count: 0,
  critical_count: 0,
  warning_count: 0,
  info_count: 0,
  llm_pending_count: 0,
  simulated_count: 0,
};

export const useApiStore = create<ApiState>((set, get) => ({
  authState: UNRESOLVED_AUTH_STATE,
  authStatus: UNKNOWN_AUTH_STATUS,
  authErrorKey: null,
  authNoticeKey: null,
  authBusy: false,
  nodes: [],
  edges: [],
  sources: [],
  normalizedMarkets: [],
  marketSpreads: [],
  marketQuotes: [],
  intradayOpportunities: [],
  /**
   * Architecture V2 Wave 5: the coherent market read model the market lane
   * refreshes. Surfaces read it for the single as-of and per-slice freshness;
   * the row slices above stay the rendering input.
   */
  marketContext: null,
  portfolioSnapshot: null,
  reviewContext: null,
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
  monitoringSummary: {
    open_count: 0,
    acknowledged_count: 0,
    critical_count: 0,
    warning_count: 0,
    info_count: 0,
    llm_pending_count: 0,
    simulated_count: 0,
  },
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
  endpointRetryBusy: false,
  endpointRetryAttempts: 0,
  endpointRetryLastAttemptAtUtc: null,
  meta: null,
  analysisSnapshots: [],
  analysisSnapshotSource: null,
  snapshotMessage: null,
  reviewSnapshotId: null,
  marketLastUpdatedAtUtc: null,
  loading: false,
  streamingActive: false,
  error: null,
  credentialMessage: null,
  contractSaveMessage: null,
  sourceRunOutcome: null,
  jobs: [],
  dataProducts: null,
  agentRuns: [],
  dataStatus: "unavailable",

  bootstrapIdentity: async () => {
    // Identity first: no workspace, market, monitoring or stream request may be
    // issued before this resolves to an authenticated session.
    const requestGeneration = identityReadCoordinator.capture();
    set((state) => ({
      authState: bootstrapStartState(state.authState),
      authErrorKey: null,
      authNoticeKey: null,
    }));
    closeDecisionStreams();
    const [meOutcome, statusResult] = await Promise.all([
      loadWorkspaceEndpoint(api.me, {
        retries: 0,
        timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
      }),
      loadWorkspaceEndpoint(api.authStatus, {
        retries: 0,
        timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
      }),
    ]);
    if (!identityReadCoordinator.isCurrent(requestGeneration)) return;
    const authStatus = statusResult.ok
      ? authStatusSnapshot(statusResult.value.data)
      : get().authStatus;
    const identity = resolveIdentity(meOutcome);
    if (!meOutcome.ok) {
      invalidateIdentitySession();
      set({
        ...resetIdentityScopedCaches(DEFAULT_MONITORING_SUMMARY),
        authStatus,
        authErrorKey: identityFailureKey(identity.failureReason),
      });
      return;
    }
    const csrf = meOutcome.value.data.csrf_token;
    if (csrf) {
      const { setDesktopSessionToken } = await import("@/api/client");
      if (!identityReadCoordinator.isCurrent(requestGeneration)) return;
      // Browser sessions use the cookie; CSRF token is kept in memory for
      // cookie-authenticated mutations.
      setDesktopSessionToken("", csrf);
    }
    set({
      authState: AUTHENTICATED_AUTH_STATE,
      authStatus,
      authErrorKey: null,
      currentUser: meOutcome.value.data,
    });
  },

  login: async (username, password) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ authBusy: true, authErrorKey: null, authNoticeKey: null });
    try {
      // The backend validates the credential and sets the HttpOnly session
      // cookie; this response is never treated as an access decision.
      const response = await api.login(username, password);
      if (!identityReadCoordinator.isCurrent(requestGeneration) || logoutInProgress) return;
      set({
        authState: AUTHENTICATED_AUTH_STATE,
        authBusy: false,
        authErrorKey: null,
        currentUser: devLoginCurrentUser(response.data),
      });
      // Replace the provisional projection with the authoritative identity read.
      await get().fetchMe();
    } catch (error) {
      if (!identityReadCoordinator.isCurrent(requestGeneration)) return;
      invalidateIdentitySession();
      set({
        ...resetIdentityScopedCaches(DEFAULT_MONITORING_SUMMARY),
        authBusy: false,
        authErrorKey: devLoginErrorKey(String(error)),
      });
    }
  },

  fetchWorkspace: async () => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    const load = startWorkspaceLoad();
    set({ loading: true, error: null });
    const releaseOutcome = await loadWorkspaceEndpoint(api.runtimeRelease, {
      signal: load.signal,
      timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
    });
    if (!workspaceLoadCoordinator.isCurrent(load.generation, load.signal)) {
      workspaceLoadCoordinator.finish(load.generation);
      return;
    }
    if (releaseOutcome.ok) {
      const releaseCompatibility = compatibilityForServer(
        CLIENT_RELEASE_METADATA,
        releaseOutcome.value.data as RuntimeReleaseDTO,
      );
      set({ runtimeRelease: releaseOutcome.value.data as RuntimeReleaseDTO, releaseCompatibility });
    } else {
      set({
        runtimeRelease: null,
        releaseCompatibility: compatibilityForServer(CLIENT_RELEASE_METADATA, null),
      });
    }
    const outcomes = await loadWorkspaceEndpoints(WORKSPACE_LOADERS, {
      signal: load.signal,
      timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
    });
    if (!workspaceLoadCoordinator.isCurrent(load.generation, load.signal)) {
      workspaceLoadCoordinator.finish(load.generation);
      return;
    }
    const identityReset = identityDeniedWorkspaceReset(outcomes, DEFAULT_MONITORING_SUMMARY);
    if (identityReset) {
      invalidateIdentitySession();
      set({ ...identityReset, authErrorKey: SESSION_EXPIRED_KEY });
      return;
    }
    const workspaceCommit = commitWorkspaceLoad(outcomes);
    const { endpointErrors, endpointErrorCodes } = workspaceCommit;
    const endpointMeta: Record<string, ApiMeta> = {};
    const slices: Record<string, unknown> = {};
    for (const { key, outcome } of outcomes) {
      if (outcome.ok) {
        endpointMeta[key] = outcome.value.meta;
        slices[key] = deriveWorkspaceSlice(key, outcome.value);
      }
    }
    const sourceRefs = Object.values(endpointMeta).flatMap((item) => item.source_references ?? []);
    const hasRuntime = sourceRefs.some((source) => source === "runtime-postgresql");
    const hasDbMissing = sourceRefs.some((source) => source === "runtime-db-not-configured");
    const runtimeDb = slices.runtimeDb as RuntimeDbStatusDTO | undefined;
    // The portfolio projection fills three state fields from one payload, so the
    // batch maps it through the same applier the retry path uses.
    const portfolioLane = applyPortfolioSnapshot(
      get(),
      (slices.portfolioSnapshot ?? null) as PortfolioSnapshotProjectionDTO | null,
    );
    const allFailed = Object.keys(endpointErrors).length === WORKSPACE_LOADERS.length;
    const resolvedStatus =
      !runtimeDb || !runtimeDb.database_url_present || !runtimeDb.connectivity.ok
        ? "unavailable"
        : hasRuntime && hasDbMissing
          ? "partial"
          : hasRuntime
            ? "runtime"
            : "partial";

    set({
      nodes: (slices.referenceNodes ?? []) as NodeDTO[],
      edges: (slices.referenceEdges ?? []) as EdgeDTO[],
      sources: (slices.sources ?? []) as SourceSystemDTO[],
      normalizedMarkets: (slices.normalizedMarkets ?? []) as NormalizedMarketObsDTO[],
      marketSpreads: (slices.marketSpreads ?? []) as MarketSpreadDTO[],
      marketQuotes: (slices.marketQuotes ?? []) as MarketQuoteDTO[],
      intradayOpportunities: (slices.intradayOpportunities ?? []) as IntradayOpportunityDTO[],
      screenOrders: portfolioLane.screenOrders,
      pnlSnapshots: portfolioLane.pnlSnapshots,
      portfolioSummary: portfolioLane.portfolioSummary,
      portfolioSnapshot: portfolioLane.portfolioSnapshot,
      fxRates: (slices.fxRates ?? []) as FxRateDTO[],
      flows: (slices.flows ?? []) as FlowObsDTO[],
      capacity: (slices.capacity ?? []) as CapacityObsDTO[],
      storage: (slices.storage ?? []) as StorageObsDTO[],
      lng: (slices.lng ?? []) as LngObsDTO[],
      tsoAccess: (slices.tsoAccess ?? []) as TsoAccessPointDTO[],
      routes: (slices.routes ?? []) as RouteEligibilityDTO[],
      routeCandidates: (slices.routeCandidates ?? []) as RouteCandidateDTO[],
      tsoTariffs: (slices.tsoTariffs ?? []) as TsoTariffDTO[],
      upstreamContracts: (slices.upstreamContracts ?? []) as UpstreamContractDTO[],
      resourcePoolOptions: portfolioLane.resourcePoolOptions,
      glossaryTerms: (slices.glossaryTerms ?? []) as GlossaryTermDTO[],
      runtimeDb: (slices.runtimeDb ?? null) as RuntimeDbStatusDTO | null,
      runtimeDependencies: (slices.runtimeDependencies ?? null) as RuntimeDependenciesDTO | null,
      runtimeRelease: get().runtimeRelease,
      releaseCompatibility: get().releaseCompatibility,
      credentialProviders: (slices.credentialProviders ?? []) as CredentialProviderDTO[],
      monitoringAlerts: (slices.monitoringAlerts ?? []) as MonitoringAlertDTO[],
      monitoringSummary: (slices.monitoringSummary ?? DEFAULT_MONITORING_SUMMARY) as MonitoringSummaryDTO,
      reviewDecisions: (slices.reviewDecisions ?? []) as ReviewDecisionDTO[],
      pipelineHealth: (slices.pipelineHealth ?? null) as PipelineHealthDTO | null,
      // currentUser is owned by the identity reads (bootstrapIdentity/fetchMe);
      // a workspace batch must never rewrite identity.
      endpointMeta,
      endpointErrors,
      endpointErrorCodes,
      meta: endpointMeta.referenceNodes ?? null,
      marketLastUpdatedAtUtc: latestMarketObservedAt(
        (slices.normalizedMarkets ?? []) as NormalizedMarketObsDTO[],
        (slices.marketQuotes ?? []) as MarketQuoteDTO[],
        (slices.fxRates ?? []) as FxRateDTO[],
      ),
      dataStatus: resolvedStatus,
      loading: workspaceCommit.loading,
      error: allFailed ? workspaceCommit.error : null,
    });
    void get().fetchStrategySummary();
    void get().fetchStrategyRuns();
    void get().fetchMe();
    get().subscribeDecisionStreams();
    workspaceLoadCoordinator.finish(load.generation);
  },

  retryFailedWorkspaceEndpoints: async () => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    // One bounded attempt at a time. The control is also disabled while an
    // attempt runs, but the refusal is authoritative here so a second caller
    // can never stack another pass with its own timeout budget.
    if (get().endpointRetryBusy) return;
    const failedKeys = Object.keys(get().endpointErrors);
    if (failedKeys.length === 0) return;
    const loaderByKey = new Map([...WORKSPACE_LOADERS, ...RETRY_ONLY_LOADERS]);
    const retryableLoaders = knownWorkspaceLoaders(failedKeys, loaderByKey);
    if (retryableLoaders.length === 0) return;

    const load = startWorkspaceLoad();
    set((state) => ({
      loading: true,
      error: null,
      endpointRetryBusy: true,
      endpointRetryAttempts: state.endpointRetryAttempts + 1,
      endpointRetryLastAttemptAtUtc: new Date().toISOString(),
    }));
    try {
      const outcomes = await loadWorkspaceEndpoints(retryableLoaders, {
        signal: load.signal,
        timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
      });
      if (!workspaceLoadCoordinator.isCurrent(load.generation, load.signal)) return;
      const identityReset = identityDeniedWorkspaceReset(outcomes, DEFAULT_MONITORING_SUMMARY);
      if (identityReset) {
        invalidateIdentitySession();
        set({ ...identityReset, authErrorKey: SESSION_EXPIRED_KEY });
        return;
      }
      set((state) => {
        const endpointErrors = { ...state.endpointErrors };
        const endpointErrorCodes = { ...state.endpointErrorCodes };
        const endpointMeta = { ...state.endpointMeta };
        const patch: Partial<ApiState> = {};
        for (const { key, outcome } of outcomes) {
          if (outcome.ok) {
            delete endpointErrors[key];
            delete endpointErrorCodes[key];
            endpointMeta[key] = outcome.value.meta;
            // A projection lane carries several ApiState fields, so a retried read
            // re-derives every field it feeds rather than only the payload.
            const applyProjection = PROJECTION_LANE_APPLIERS[key];
            if (applyProjection) {
              Object.assign(patch, applyProjection(state, outcome.value.data));
              continue;
            }
            const stateKey = WORKSPACE_STATE_KEYS[key];
            if (stateKey) {
              (patch as Record<string, unknown>)[stateKey] = deriveWorkspaceSlice(key, outcome.value);
            }
          } else {
            endpointErrors[key] = outcome.error.message;
            endpointErrorCodes[key] = outcome.error.code;
          }
        }
        return {
          ...patch,
          endpointErrors,
          endpointErrorCodes,
          endpointMeta,
          error: Object.keys(endpointErrors).length === 0 ? null : state.error,
          loading: false,
        };
      });
    } finally {
      const current = workspaceLoadCoordinator.isCurrent(load.generation, load.signal);
      workspaceLoadCoordinator.finish(load.generation);
      // The attempt owns the busy flag: it clears even when a newer workspace
      // load superseded this pass, so the retry control cannot stay disabled.
      set(current ? { loading: false, endpointRetryBusy: false } : { endpointRetryBusy: false });
    }
  },

  refreshMarketData: async () => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    const refresh = readRefreshCoordinator.market.tryStart();
    if (!refresh) return;
    const refreshGeneration = readRefreshCoordinator.currentGeneration();
    const refreshSequence = ++marketRefreshSequence;
    const options = {
      signal: refresh.signal,
      retries: 0,
      timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
    };
    try {
      // Architecture V2 Wave 5: the market lane reads ONE coherent projection
      // (one as-of, one time basis, per-slice freshness) instead of joining five
      // low-level endpoints and reconciling their timestamps client-side. Source
      // posture stays independent inside the same lane.
      const sourcesPromise = loadWorkspaceEndpoint(api.sources, options);
      const [contextResult, fxResult] = await Promise.all([
        loadWorkspaceEndpoint((loaderOptions) => api.marketContext(undefined, loaderOptions), options),
        loadWorkspaceEndpoint(api.fxRates, options),
      ]);
      if (
        refreshSequence === marketRefreshSequence &&
        readRefreshCoordinator.isCurrent(refreshGeneration)
      ) {
        set((state) => {
          const endpointMeta = { ...state.endpointMeta };
          const endpointErrors = { ...state.endpointErrors };
          const endpointErrorCodes = { ...state.endpointErrorCodes };
          const recordOutcome = (
            key: string,
            outcome: WorkspaceLoaderOutcome<{ data: unknown; meta: ApiMeta }>,
          ) => {
            if (outcome.ok) {
              endpointMeta[key] = outcome.value.meta;
              delete endpointErrors[key];
              delete endpointErrorCodes[key];
            } else {
              endpointErrors[key] = outcome.error.message;
              endpointErrorCodes[key] = outcome.error.code;
            }
          };
          recordOutcome("marketContext", contextResult);
          recordOutcome("fxRates", fxResult);

          // The projection is the market surface's coherent source. Its slices are
          // mapped into the same state fields the surfaces already read, so no
          // downstream model changes - but every value now comes from one payload
          // with one as-of. A projection the backend could not serve leaves the
          // previous values in place instead of inventing an empty market.
          const projection = contextResult.ok ? contextResult.value.data : null;
          const fxRates = fxResult.ok ? fxResult.value.data : state.fxRates;
          const failedMarketEndpoints = ["marketContext", "fxRates"].filter(
            (key) => endpointErrors[key],
          );

          return {
            ...applyMarketContext(state, projection, fxRates),
            fxRates,
            endpointMeta,
            endpointErrors,
            endpointErrorCodes,
            meta: contextResult.ok ? contextResult.value.meta : state.meta,
            error: failedMarketEndpoints.length > 0
              ? `${MARKET_REFRESH_ERROR_PREFIX} ${failedMarketEndpoints.join(", ")}`
              : state.error?.startsWith(MARKET_REFRESH_ERROR_PREFIX)
                ? null
                : state.error,
          };
        });
      }
      const sources = await sourcesPromise;
      if (
        refreshSequence === marketRefreshSequence &&
        readRefreshCoordinator.isCurrent(refreshGeneration) &&
        sources.ok
      ) {
        set((state) => ({
          sources: sources.value.data,
          endpointMeta: { ...state.endpointMeta, sources: sources.value.meta },
          endpointErrors: Object.fromEntries(
            Object.entries(state.endpointErrors).filter(([key]) => key !== "sources"),
          ),
          endpointErrorCodes: Object.fromEntries(
            Object.entries(state.endpointErrorCodes).filter(([key]) => key !== "sources"),
          ),
        }));
      } else if (
        refreshSequence === marketRefreshSequence &&
        readRefreshCoordinator.isCurrent(refreshGeneration) &&
        !sources.ok
      ) {
        set((state) => ({
          endpointErrors: { ...state.endpointErrors, sources: sources.error.message },
          endpointErrorCodes: { ...state.endpointErrorCodes, sources: sources.error.code },
        }));
      }
    } finally {
      refresh.release();
    }
  },

  subscribeDecisionStreams: () => {
    // Streams carry protected market and monitoring payloads, so they open only
    // for an authenticated session and are closed by every identity change.
    if (!isIdentityGateOpen(get().authState)) return;
    closeDecisionStreams();
    const streamGeneration = identityReadCoordinator.capture();
    const streamIsCurrent = () => identityReadCoordinator.isCurrent(streamGeneration);
    const onStatus = (status: "open" | "error") => {
      if (streamIsCurrent()) set({ streamingActive: status === "open" });
    };

    decisionStreamClosers.push(
      openEventStream(
        "/stream/quotes",
        {
          quotes: (payload) => {
            if (!streamIsCurrent()) return;
            const quote = payload as MarketQuoteDTO;
            if (!quote || typeof quote !== "object" || !("quote_id" in quote)) return;
            set((state) => ({
              marketQuotes: mergeMarketQuotes(state.marketQuotes, [quote]),
              marketLastUpdatedAtUtc: latestTimestamp([
                state.marketLastUpdatedAtUtc,
                quote.observed_at_utc,
              ]),
            }));
          },
        },
        onStatus,
      ).close,
    );

    decisionStreamClosers.push(
      openEventStream("/stream/opportunities", {
        opportunities: (payload) => {
          if (!streamIsCurrent()) return;
          const opportunity = payload as IntradayOpportunityDTO;
          if (
            !opportunity ||
            typeof opportunity !== "object" ||
            !("opportunity_id" in opportunity)
          ) {
            return;
          }
          set((state) => ({
            intradayOpportunities: mergeIntradayOpportunities(
              state.intradayOpportunities,
              [opportunity],
            ),
          }));
        },
      }).close,
    );

    decisionStreamClosers.push(
      openEventStream("/stream/alerts", {
        alerts: (payload) => {
          if (!streamIsCurrent()) return;
          const alert = payload as MonitoringAlertDTO;
          if (!alert || typeof alert !== "object" || !("alert_id" in alert)) return;
          set((state) => ({
            monitoringAlerts: [
              alert,
              ...state.monitoringAlerts.filter((item) => item.alert_id !== alert.alert_id),
            ],
          }));
        },
      }).close,
    );
  },

  fetchMe: async () => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    try {
      const outcome = await loadWorkspaceEndpoint(api.me, {
        retries: 0,
        timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
      });
      if (!identityReadCoordinator.isCurrent(requestGeneration)) return;
      if (!outcome.ok) {
        const identity = resolveIdentity(outcome);
        invalidateIdentitySession();
        set({
          ...resetIdentityScopedCaches(DEFAULT_MONITORING_SUMMARY),
          authErrorKey: identityFailureKey(identity.failureReason),
        });
        return;
      }
      const response = outcome.value;
      const csrf = response.data.csrf_token;
      if (csrf) {
        const { setDesktopSessionToken } = await import("@/api/client");
        if (!identityReadCoordinator.isCurrent(requestGeneration)) return;
        // Browser sessions use the cookie; CSRF token is kept in memory for
        // cookie-authenticated mutations.
        setDesktopSessionToken("", csrf);
      }
      set({ authState: AUTHENTICATED_AUTH_STATE, authErrorKey: null, currentUser: response.data });
    } catch (error) {
      if (!identityReadCoordinator.isCurrent(requestGeneration)) return;
      if (isIdentityDenied(error)) {
        invalidateIdentitySession();
        set({
          ...resetIdentityScopedCaches(DEFAULT_MONITORING_SUMMARY),
          authErrorKey: SESSION_EXPIRED_KEY,
        });
      }
    }
  },

  signIn: async () => {
    if (logoutInProgress) return;
    const signInGeneration = identityReadCoordinator.capture();
    const signInIsCurrent = () =>
      !logoutInProgress && identityReadCoordinator.isCurrent(signInGeneration);
    const failSignIn = (error: unknown) => {
      set({
        authState: UNAUTHENTICATED_AUTH_STATE,
        authBusy: false,
        authErrorKey: oidcSignInErrorKey(String(error)),
      });
    };
    set({ authBusy: true, authErrorKey: null, authNoticeKey: null });
    const client = await import("@/api/client");
    if (!signInIsCurrent()) return;
    // Desktop detection and native calls belong to the single HostCapabilities
    // boundary (Architecture V2 rule 50); this store must not re-implement them.
    const isDesktop = isDesktopHost();
    if (!isDesktop) {
      // Browser SSO leaves the client; the callback re-enters through /me.
      window.location.assign(`${client.configuredApiBaseUrl()}/auth/oidc/login`);
      return;
    }
    try {
      const redirectUri = await requireHostCommand<string>(HOST_COMMANDS.startLoopbackAuth);
      const verifier = generatePkceVerifier();
      const challenge = await generatePkceChallenge(verifier);
      const started = await client.api.startDesktopOidcLogin({
        code_challenge: challenge,
        code_verifier: verifier,
        redirect_uri: redirectUri,
      });
      const query = await requireHostCommand<string>(HOST_COMMANDS.openBrowserLoginAndWait, {
        authorizationUrl: started.data.authorization_url,
        expectedRedirectUri: redirectUri,
      });
      const params = new URLSearchParams(query);
      const code = params.get("code") ?? "";
      const state = params.get("state") ?? "";
      if (!code || !state) throw new Error("Desktop login callback was incomplete.");
      if (!signInIsCurrent()) return;
      const token = await client.api.desktopOidcToken({
        code,
        state,
        code_verifier: verifier,
        redirect_uri: redirectUri,
      });
      if (!signInIsCurrent()) return;
      client.setDesktopSessionToken(token.data.access_token);
      await get().fetchMe();
      if (signInIsCurrent()) set({ authBusy: false });
    } catch (error) {
      if (signInIsCurrent()) failSignIn(error);
    }
  },

  signOut: async () => {
    logoutInProgress = true;
    // Fail closed first: the terminal unmounts and every identity-scoped slice
    // is cleared before the (best-effort) server-side revocation runs.
    invalidateIdentitySession();
    set({
      ...resetIdentityScopedCaches(DEFAULT_MONITORING_SUMMARY),
      authNoticeKey: "auth.notice_signed_out",
      authErrorKey: null,
    });
    try {
      // The logout route needs a valid credential, so client-stored auth is
      // cleared only after the revocation attempt.
      await withAbortTimeout(
        (signal) => api.logout({ signal }),
        DEFAULT_LOGOUT_TIMEOUT_MS,
      );
    } catch {
      // Server-side session may already be gone; local state is still cleared.
    } finally {
      try {
        const { clearStoredAuth, clearDesktopSessionData } = await import("@/api/client");
        clearStoredAuth();
        // Desktop shells additionally drop the WebView's cookies, caches and
        // local storage, so a shared workstation keeps nothing behind.
        await clearDesktopSessionData();
        set({ authState: UNAUTHENTICATED_AUTH_STATE, authBusy: false });
      } finally {
        logoutInProgress = false;
      }
    }
  },

  refreshMonitoring: async () => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    const refresh = readRefreshCoordinator.monitoring.tryStart();
    if (!refresh) return;
    const refreshGeneration = readRefreshCoordinator.currentGeneration();
    try {
      const [alerts, summary, health] = await Promise.all([
        loadWorkspaceEndpoint(api.monitoringAlerts, {
          signal: refresh.signal,
          retries: 0,
          timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
        }),
        loadWorkspaceEndpoint(api.monitoringSummary, {
          signal: refresh.signal,
          retries: 0,
          timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
        }),
        loadWorkspaceEndpoint(api.pipelineHealth, {
          signal: refresh.signal,
          retries: 0,
          timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
        }),
      ]);
      if (!readRefreshCoordinator.isCurrent(refreshGeneration)) return;
      if (!alerts.ok || !summary.ok || !health.ok) {
        const failures: Array<{ key: string; message: string; code: WorkspaceEndpointFailureCode }> = [];
        if (!alerts.ok) failures.push({ key: "monitoringAlerts", ...alerts.error });
        if (!summary.ok) failures.push({ key: "monitoringSummary", ...summary.error });
        if (!health.ok) failures.push({ key: "pipelineHealth", ...health.error });
        set((state) => {
          const endpointErrors = { ...state.endpointErrors };
          const endpointErrorCodes = { ...state.endpointErrorCodes };
          failures.forEach(({ key, message, code }) => {
            endpointErrors[key] = message;
            endpointErrorCodes[key] = code;
          });
          return {
            endpointErrors,
            endpointErrorCodes,
            error: `Monitoring refresh failed: ${failures.map(({ key }) => key).join(", ")}`,
          };
        });
        return;
      }
      set((state) => {
        const endpointErrors = { ...state.endpointErrors };
        const endpointErrorCodes = { ...state.endpointErrorCodes };
        ["monitoringAlerts", "monitoringSummary", "pipelineHealth"].forEach((key) => {
          delete endpointErrors[key];
          delete endpointErrorCodes[key];
        });
        return {
          monitoringAlerts: alerts.value.data,
          monitoringSummary: summary.value.data,
          pipelineHealth: health.value.data,
          endpointErrors,
          endpointErrorCodes,
          endpointMeta: {
            ...state.endpointMeta,
            monitoringAlerts: alerts.value.meta,
            monitoringSummary: summary.value.meta,
            pipelineHealth: health.value.meta,
          },
        };
      });
    } finally {
      refresh.release();
    }
  },

  fetchReviewContext: async () => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    // The review lane coalesces repeat opens: a second request while one is in flight is
    // the same question, and the answer would be the same payload.
    const refresh = readRefreshCoordinator.review.tryStart();
    if (!refresh) return;
    const refreshGeneration = readRefreshCoordinator.currentGeneration();
    try {
      const result = await loadWorkspaceEndpoint(
        (loaderOptions) => api.reviewContext(undefined, loaderOptions),
        {
          signal: refresh.signal,
          retries: 0,
          timeoutMs: DEFAULT_WORKSPACE_READ_TIMEOUT_MS,
        },
      );
      if (!readRefreshCoordinator.isCurrent(refreshGeneration)) return;
      set((state) => {
        const endpointMeta = { ...state.endpointMeta };
        const endpointErrors = { ...state.endpointErrors };
        const endpointErrorCodes = { ...state.endpointErrorCodes };
        if (result.ok) {
          delete endpointErrors.reviewContext;
          delete endpointErrorCodes.reviewContext;
          endpointMeta.reviewContext = result.value.meta;
        } else {
          endpointErrors.reviewContext = result.error.message;
          endpointErrorCodes.reviewContext = result.error.code;
        }
        const projection = result.ok ? result.value.data : null;
        const usable = reviewIsUsable(projection);
        return {
          reviewContext: projection,
          // A payload the backend could not serve leaves the review surface with the
          // decisions it already had instead of an empty review.
          reviewDecisions: usable ? reviewDecisions(projection) : state.reviewDecisions,
          endpointMeta,
          endpointErrors,
          endpointErrorCodes,
        };
      });
    } finally {
      refresh.release();
    }
  },

  /**
   * Read the deployment's recent Analysis Snapshots for the reproducibility picker.
   *
   * This is a task-scoped read rather than part of the startup batch: the reference list is
   * only needed by a surface that can cite one. A failed read leaves the picker empty and says
   * so; the source the backend cited is kept so an empty list caused by a deployment without a
   * runtime database is not mistaken for "nothing was ever recorded".
   */
  fetchAnalysisSnapshots: async () => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    const requestGeneration = identityReadCoordinator.capture();
    try {
      const result = await api.analysisSnapshots({ limit: SNAPSHOT_PICKER_LIMIT });
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({
        analysisSnapshots: result.data,
        analysisSnapshotSource: result.meta.source_references[0] ?? null,
      });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ analysisSnapshots: [], analysisSnapshotSource: null, error: String(e) });
    }
  },

  publishJobsRead: (jobs) => {
    // Publishing a read is not authority: this only lets the Inspector show a job the timeline
    // already fetched, and clearing it (an empty list) removes detail rather than inventing it.
    set({ jobs });
  },

  publishDataProductsRead: (catalogue) => {
    // Same rule for the catalogue: a failed read publishes null, so the Inspector says it cannot
    // show a product rather than showing an empty one.
    set({ dataProducts: catalogue });
  },

  publishAgentRunsRead: (agentRuns) => {
    set({ agentRuns });
  },

  requestSourceRun: async (sourceId, reason) => {
    if (logoutInProgress) return;
    if (!isIdentityGateOpen(get().authState)) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ sourceRunOutcome: null, error: null });
    try {
      const response = await api.requestSourceRun(sourceId, reason);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      // The queued run is shown from the response: the worker's progress is a separate read.
      set({ sourceRunOutcome: sourceRunOutcome(response.data), loading: false });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ sourceRunOutcome: null, error: String(e) });
    }
  },

  setReviewSnapshotId: (snapshotId) => {    // The selection is a choice among references the deployment recorded; clearing it means
    // the next run cites nothing and its payload stays exactly as it was.
    set({ reviewSnapshotId: snapshotId });
  },

  recordAnalysisSnapshot: async (context, runtimeDbReady) => {
    if (logoutInProgress) return null;
    if (!isIdentityGateOpen(get().authState)) return null;
    const readiness = analysisSnapshotReadiness({ context: snapshotContextFrom(context), runtimeDbReady, recording: false });
    // The rule decides, and the surface shows the same blockers: refusing here is the same
    // answer the button's disabled state already gave.
    if (!readiness.canRecord) return readiness.firstBlockerKey;
    const requestGeneration = identityReadCoordinator.capture();
    set({ snapshotMessage: null });
    try {
      const response = await api.createAnalysisSnapshot(
        analysisSnapshotRequest(snapshotContextFrom(context), new Date().toISOString()),
      );
      if (!followUpReadIsCurrent(requestGeneration)) return null;
      // Read the list back from the backend rather than appending the response: the record the
      // deployment holds is the evidence, and the response is only what it said it wrote.
      const recorded = response.data.snapshot_id;
      set({ reviewSnapshotId: recorded, snapshotMessage: "recorded" });
      await get().fetchAnalysisSnapshots();
      return "recorded";
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return null;
      // A refusal is reported as itself: an unknown context key, an unavailable store or a
      // failed write must not read as a recorded snapshot.
      set({ snapshotMessage: null, error: String(e) });
      return "failed";
    }
  },

  saveProviderCredential: async (providerId, apiKey, label) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ credentialMessage: null });
    try {
      await api.saveCredential(providerId, { api_key: apiKey, label });
      if (!followUpReadIsCurrent(requestGeneration)) return;
      const credentialProviders = await api.credentialProviders();
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({
        credentialProviders: credentialProviders.data,
        credentialMessage: `${providerId} credential saved.`,
      });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ credentialMessage: String(e) });
    }
  },

  testProviderConnection: async (providerId) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ credentialMessage: null });
    try {
      const result = await api.testCredentialConnection(providerId);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      const credentialProviders = await api.credentialProviders();
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({
        credentialProviders: credentialProviders.data,
        credentialMessage: result.data.connection_status === "success"
          ? `${providerId} live connection passed.`
          : `${providerId} live connection failed: ${result.data.connection_error_code ?? result.data.connection_status}`,
      });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ credentialMessage: String(e) });
      throw e;
    }
  },

  acknowledgeMonitoringAlert: async (alertId) => {
    set({ monitoringBusyAlertId: alertId });
    try {
      await api.acknowledgeMonitoringAlert(alertId);
      const [alerts, summary] = await Promise.all([
        api.monitoringAlerts(),
        api.monitoringSummary(),
      ]);
      set({
        monitoringAlerts: alerts.data,
        monitoringSummary: summary.data,
        monitoringBusyAlertId: null,
      });
    } catch (e) {
      set({ error: String(e), monitoringBusyAlertId: null });
    }
  },

  analyzeMonitoringAlert: async (alertId, question, language) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ monitoringBusyAlertId: alertId });
    try {
      const result = await api.analyzeMonitoringAlert(alertId, {
        question,
        language,
        model: "deepseek-v4-flash",
      });
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set((state) => ({
        monitoringAnalysisByAlert: {
          ...state.monitoringAnalysisByAlert,
          [alertId]: result.data,
        },
        monitoringBusyAlertId: null,
      }));
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ error: String(e), monitoringBusyAlertId: null });
    }
  },

  saveDraftContract: async (contract) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ contractSaveMessage: null, loading: true, error: null });
    try {
      const saved = await api.saveUpstreamContract(contract);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      const [upstreamContracts, resourcePoolOptions] = await Promise.all([
        api.upstreamContracts(),
        api.resourcePoolOptions(),
      ]);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({
        upstreamContracts: upstreamContracts.data,
        resourcePoolOptions: resourcePoolOptions.data,
        meta: saved.meta,
        contractSaveMessage: `${saved.data.contract_id} persisted for decision support.`,
        loading: false,
      });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ error: String(e), contractSaveMessage: String(e), loading: false });
    }
  },

  recordReviewDecision: async (body) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ reviewMessage: null });
    try {
      const saved = await api.recordReviewDecision(body);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      const list = await api.reviewDecisions();
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({
        reviewDecisions: list.data,
        reviewMessage: `${saved.data.decision_id} recorded for ${saved.data.entity_type}:${saved.data.entity_id}.`,
      });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ reviewMessage: String(e) });
    }
  },

  recommendRouteAllocation: async (request) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ loading: true, error: null });
    try {
      const result = await api.recommendRouteAllocation(request);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ routeRecommendation: result.data, meta: result.meta, loading: false });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ error: String(e), loading: false });
    }
  },

  optimizeResourcePool: async (request) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ loading: true, error: null });
    try {
      const result = await api.optimizeResourcePool(withoutLegacyFlag(request));
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ resourcePoolResult: result.data, meta: result.meta, loading: false });
    } catch (e) {
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ error: String(e), loading: false });
    }
  },

  evaluateStrategyLab: async (scenario) => {
    set({ loading: true, error: null });
    try {
      const result = await api.evaluateStrategyLab(withoutLegacyFlag(scenario));
      set({ strategyResult: result.data, meta: result.meta, loading: false });
      void get().fetchStrategySummary();
      void get().fetchStrategyRuns();
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  fetchStrategySummary: async () => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    try {
      const result = await api.strategySummary({ strategy_id: DEFAULT_STRATEGY_ID });
      if (!identityReadCoordinator.isCurrent(requestGeneration) || logoutInProgress) return;
      set({ strategySummary: result.data });
    } catch (e) {
      if (identityReadCoordinator.isCurrent(requestGeneration) && !logoutInProgress) {
        set({ strategySummary: null, error: String(e) });
      }
    }
  },

  fetchStrategyRuns: async () => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    try {
      const result = await api.strategyRuns({ strategy_id: DEFAULT_STRATEGY_ID, limit: 20 });
      if (!identityReadCoordinator.isCurrent(requestGeneration) || logoutInProgress) return;
      set({ strategyRuns: result.data });
    } catch (e) {
      if (identityReadCoordinator.isCurrent(requestGeneration) && !logoutInProgress) {
        set({ strategyRuns: [], error: String(e) });
      }
    }
  },

  fetchGlossaryContext: async (term, params) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ loading: true, error: null });
    try {
      const result = await api.glossaryContext(term, params);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ glossaryContext: result.data, meta: result.meta, loading: false });
    } catch (e) {
      if (followUpReadIsCurrent(requestGeneration)) {
        set({ error: String(e), loading: false });
      }
    }
  },

  askAnalysis: async (body) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ loading: true, error: null });
    try {
      const result = await api.analysisQuery(body);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ analysisResult: result.data, meta: result.meta, loading: false });
    } catch (e) {
      if (followUpReadIsCurrent(requestGeneration)) {
        set({ error: String(e), loading: false });
      }
    }
  },

  generatePortfolioReport: async (body) => {
    if (logoutInProgress) return;
    const requestGeneration = identityReadCoordinator.capture();
    set({ loading: true, error: null });
    try {
      const result = await api.portfolioReport(body);
      if (!followUpReadIsCurrent(requestGeneration)) return;
      set({ analysisResult: result.data, meta: result.meta, loading: false });
    } catch (e) {
      if (followUpReadIsCurrent(requestGeneration)) {
        set({ error: String(e), loading: false });
      }
    }
  },
}));
