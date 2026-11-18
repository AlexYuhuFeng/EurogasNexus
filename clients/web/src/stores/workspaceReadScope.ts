import type { CurrentUserDTO } from "../api/client";

/** Request composition only. Every request remains authorised by the backend. */
export function needsCommercialWorkspaceReads(user: CurrentUserDTO | null): boolean {
  if (user?.experience) return user.experience.commercial_capabilities.length > 0;
  // Compatibility with identity responses predating the experience projection.
  // ADMIN is an administration bundle; overlapping commercial roles still compose reads.
  if (!user) return true;
  const roles = user.roles?.length ? user.roles : [user.role];
  return roles.some((role) => role !== "ADMIN");
}

const COMMERCIAL_WORKSPACE_KEYS = new Set([
  "normalizedMarkets", "marketSpreads", "marketQuotes", "intradayOpportunities",
  "portfolioSnapshot", "fxRates", "routes", "routeCandidates", "tsoTariffs",
  "upstreamContracts", "monitoringAlerts", "monitoringSummary", "reviewDecisions",
  "marketContext", "reviewContext",
]);

/** Raw editable resource terms belong to scenario preparation. Reviewers read
 * persisted case evidence and portfolio projections instead of issuing this
 * governed preparation read. This is composition, never an authorization gate. */
export function workspaceReadNeeded(key: string, user: CurrentUserDTO | null): boolean {
  if (key === "reviewDecisions" && viewerOnly(user)) {
    // GET /api/review/decisions has the REVIEWER role floor: a VIEWER-only identity is refused,
    // and the refusal read as "some data failed to load" on every page of a fresh installation.
    return false;
  }
  if (key === "upstreamContracts" && Array.isArray(user?.permissions)) {
    return needsCommercialWorkspaceReads(user) && user.permissions.includes("scenario.create");
  }
  return !COMMERCIAL_WORKSPACE_KEYS.has(key) || needsCommercialWorkspaceReads(user);
}

/**
 * Whether the identity runs governed research (spread lab, backtest experiments). The server
 * keeps those routes to the analyst role; a risk reviewer reads strategies and their runs but
 * does not issue these reads. Composition only: the backend authorises every request, and an
 * unknown identity composes the read rather than hiding it.
 */
export function runsGovernedResearch(user: CurrentUserDTO | null): boolean {
  if (!user || !Array.isArray(user.permissions)) return true;
  return user.permissions.includes("strategy.create");
}

/** An identity whose only role is VIEWER (composition only; the server decides access). */
function viewerOnly(user: CurrentUserDTO | null): boolean {
  const roles = Array.isArray(user?.roles) && user.roles.length > 0 ? user.roles : user?.role ? [user.role] : [];
  return roles.length > 0 && roles.every((role) => String(role).toUpperCase() === "VIEWER");
}

/**
 * The reads the visible page draws first: they start before the rest of the workspace batch
 * (which is bounded to a few reads at a time), so the page a reader is looking at fills first.
 */
const FIRST_READS: Record<string, readonly string[]> = {
  market: ["normalizedMarkets", "marketQuotes", "fxRates", "marketSpreads", "monitoringAlerts"],
  network: ["referenceNodes", "referenceEdges", "flows", "capacity", "storage", "lng", "tsoAccess"],
  capacity: ["capacity", "flows", "storage", "lng"],
  contracts: ["portfolioSnapshot", "upstreamContracts", "routes", "routeCandidates", "fxRates"],
  scenario: ["portfolioSnapshot", "upstreamContracts", "reviewDecisions"],
  review: ["reviewDecisions", "portfolioSnapshot"],
  sources: ["sources", "pipelineHealth"],
  runtime: ["runtimeDb", "runtimeDependencies", "pipelineHealth", "credentialProviders"],
  glossary: ["glossaryTerms"],
};

export function workspaceReadOrder(keys: readonly string[], search: string): string[] {
  const params = new URLSearchParams(search);
  const page = params.get("workspace") ?? "market";
  const task = params.get("task");
  const first = FIRST_READS[page === "market" && task === "network" ? "network" : page === "market" && task === "capacity" ? "capacity" : page] ?? [];
  const rank = (key: string) => {
    const index = first.indexOf(key);
    return index === -1 ? first.length : index;
  };
  return [...keys].sort((left, right) => rank(left) - rank(right));
}
