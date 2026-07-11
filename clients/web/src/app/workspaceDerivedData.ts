import type {
  EdgeDTO,
  NodeDTO,
  SourceCategoryPostureDTO,
  SourceSystemDTO,
} from "@/api/client";

type WarningCarrier = {
  warnings?: string[] | null;
};

type SourceLike = {
  connectivity_status: string;
  credential_state: string;
  live_record_count: number;
};

type FlowLike = {
  source_system?: string;
};

export const SOURCE_ISSUE_STATUSES = [
  "failed",
  "needs_credential",
  "credential_disabled",
  "runtime_unconfigured",
] as const;

export const SOURCE_CATEGORY_ORDER = [
  "price",
  "fx",
  "infrastructure",
  "tariff",
  "weather",
  "ai",
] as const;

export const SOURCE_CATEGORIES = ["all", ...SOURCE_CATEGORY_ORDER];

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

export function buildSourcePostureRows(
  sources: SourceSystemDTO[],
  apiRows: SourceCategoryPostureDTO[] | null | undefined,
): SourceCategoryPostureDTO[] {
  if (apiRows && apiRows.length > 0) {
    return apiRows
      .filter((row) => SOURCE_CATEGORY_ORDER.includes(row.category as typeof SOURCE_CATEGORY_ORDER[number]))
      .sort(
        (left, right) =>
          SOURCE_CATEGORY_ORDER.indexOf(left.category as typeof SOURCE_CATEGORY_ORDER[number]) -
          SOURCE_CATEGORY_ORDER.indexOf(right.category as typeof SOURCE_CATEGORY_ORDER[number]),
      );
  }

  const issueStatuses = new Set([
    ...SOURCE_ISSUE_STATUSES,
    "no_records",
  ]);
  return SOURCE_CATEGORY_ORDER.map((category) => {
    const categorySources = sources.filter((source) => source.category === category);
    return {
      category,
      category_label: category,
      registered_sources: categorySources.length,
      active_sources: categorySources.filter((source) => source.connectivity_status === "active").length,
      sources_needing_attention: categorySources.filter((source) => issueStatuses.has(source.connectivity_status)).length,
      missing_credentials: categorySources.filter((source) => source.credential_state === "missing").length,
      preview_substitutes_active: categorySources.filter((source) => source.preview_substitute_status === "active").length,
      runtime_records: categorySources.reduce((total, source) => total + source.live_record_count, 0),
      next_action: categorySources.some((source) => source.credential_state === "missing")
        ? "add_credentials"
        : categorySources.some((source) => source.connectivity_status === "failed")
          ? "inspect_failure"
          : categorySources.some((source) => source.connectivity_status === "active")
            ? "monitor"
            : "run_ingestion",
    };
  }).filter((row) => row.registered_sources > 0);
}

export function buildSourceCategoryCounts(sources: SourceSystemDTO[]): Map<string, number> {
  const counts = new Map<string, number>();
  sources.forEach((source) => counts.set(source.category, (counts.get(source.category) ?? 0) + 1));
  return counts;
}

export function buildSourcesByCategory(sources: SourceSystemDTO[]): Map<string, string[]> {
  const grouped = new Map<string, string[]>();
  sources.forEach((source) => {
    const systems = grouped.get(source.category) ?? [];
    grouped.set(source.category, [...systems, source.source_system]);
  });
  return grouped;
}

export function filterSourcesByCategory(
  sources: SourceSystemDTO[],
  category: string,
): SourceSystemDTO[] {
  return category === "all" ? sources : sources.filter((source) => source.category === category);
}

export function sourceNextActionKey(source: SourceSystemDTO | null): string {
  if (!source) return "sources.action.none";
  if (source.connectivity_status === "active") return "sources.action.monitor";
  if (source.connectivity_status === "failed") return "sources.action.inspect_failure";
  if (source.credential_state === "missing") return "sources.action.add_credential";
  if (source.credential_state === "disabled") return "sources.action.enable_credential";
  if (source.connectivity_status === "runtime_unconfigured") return "sources.action.configure_runtime";
  if (["no_records", "configured"].includes(source.connectivity_status)) {
    return "sources.action.run_ingestion";
  }
  return "sources.action.review";
}

export type NetworkGeometryState =
  | "runtime_missing"
  | "nodes_missing"
  | "edges_missing"
  | "corridors_only"
  | "loaded";

export function resolveNetworkGeometryState(
  runtimeDbReady: boolean,
  nodes: NodeDTO[],
  edges: EdgeDTO[],
): NetworkGeometryState {
  if (!runtimeDbReady) return "runtime_missing";
  if (nodes.length === 0) return "nodes_missing";
  if (edges.length === 0) return "edges_missing";
  const hasReferenceNetworkEdge = edges.some((edge) => {
    const materialization = edge.metadata_json?.materialization;
    return edge.source_system !== "route_candidate" && materialization !== "route_candidate_edge";
  });
  return hasReferenceNetworkEdge ? "loaded" : "corridors_only";
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
