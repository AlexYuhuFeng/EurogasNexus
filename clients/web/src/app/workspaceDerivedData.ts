type WarningCarrier = {
  warnings?: string[] | null;
};

type SourceLike = {
  connectivity_status: string;
  credential_state: string;
  live_record_count: number;
};

type FlowLike = {
  source_system: string;
};

export const SOURCE_ISSUE_STATUSES = [
  "failed",
  "needs_credential",
  "credential_disabled",
  "runtime_unconfigured",
] as const;

export function latestRows<T>(rows: T[], limit: number): T[] {
  return rows.slice(0, limit);
}

export function latestOfficialFlows<T extends FlowLike>(flows: T[], sourceSystem = "ENTSOG", limit = 5): T[] {
  return flows.filter((item) => item.source_system === sourceSystem).slice(0, limit);
}

export function buildReviewWarnings(
  resourcePoolResult: WarningCarrier | null | undefined,
  routeRecommendation: WarningCarrier | null | undefined,
  strategyResult: WarningCarrier | null | undefined,
  analysisResult: WarningCarrier | null | undefined,
  meta: WarningCarrier | null | undefined,
): string[] {
  return [
    ...(resourcePoolResult?.warnings ?? []),
    ...(routeRecommendation?.warnings ?? []),
    ...(strategyResult?.warnings ?? []),
    ...(analysisResult?.warnings ?? []),
    ...(meta?.warnings ?? []),
  ];
}

export function buildSourceStats(sources: SourceLike[]) {
  const issueStatuses = new Set<string>(SOURCE_ISSUE_STATUSES);
  return {
    total: sources.length,
    active: sources.filter((source) => source.connectivity_status === "active").length,
    issues: sources.filter((source) => issueStatuses.has(source.connectivity_status)).length,
    records: sources.reduce((total, source) => total + source.live_record_count, 0),
    missingCredentials: sources.filter((source) => source.credential_state === "missing").length,
  };
}

export function buildWorkspaceLatestRows<TFlow extends FlowLike, TCapacity, TTsoAccess, TTariff, TStorage, TLng>(params: {
  flows: TFlow[];
  capacity: TCapacity[];
  tsoAccess: TTsoAccess[];
  tsoTariffs: TTariff[];
  storage: TStorage[];
  lng: TLng[];
}) {
  return {
    latestOfficialFlows: latestOfficialFlows(params.flows),
    latestCapacityRows: latestRows(params.capacity, 5),
    latestTsoAccessRows: latestRows(params.tsoAccess, 6),
    latestTariffRows: latestRows(params.tsoTariffs, 6),
    latestStorageRows: latestRows(params.storage, 4),
    latestLngRows: latestRows(params.lng, 4),
  };
}
