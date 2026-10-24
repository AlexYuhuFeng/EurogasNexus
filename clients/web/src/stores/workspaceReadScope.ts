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
  if (key === "upstreamContracts" && Array.isArray(user?.permissions)) {
    return needsCommercialWorkspaceReads(user) && user.permissions.includes("scenario.create");
  }
  return !COMMERCIAL_WORKSPACE_KEYS.has(key) || needsCommercialWorkspaceReads(user);
}
