import type {
  PortfolioOptimizationResultDTO,
  ResourcePoolOptionsDTO,
  RouteRecommendationResultDTO,
} from "@/api/client";

export type CommercialDiagnosticLevel = "blocker" | "warning" | "missing_input";
export type CommercialDiagnosticOrigin =
  | "preflight"
  | "pool_options"
  | "optimizer"
  | "allocation"
  | "route_recommendation"
  | "route_exclusion";

export interface CommercialDiagnosticItem {
  raw: string;
  code: string | null;
  detail: string;
  level: CommercialDiagnosticLevel;
  origins: CommercialDiagnosticOrigin[];
  affectedResourceId: string | null;
  affectedRouteId: string | null;
  sourceSystem: string | null;
  sourceReference: string | null;
  observedAtUtc: string | null;
  freshness: string | null;
  simulated: boolean | null;
  sourceRefs: string[];
}

interface BuildCommercialDiagnosticsInput {
  poolInputBlockers?: readonly string[] | null;
  options?: ResourcePoolOptionsDTO | null;
  optimizer?: PortfolioOptimizationResultDTO | null;
  recommendation?: RouteRecommendationResultDTO | null;
}

interface DiagnosticSeed {
  raw: string;
  level: CommercialDiagnosticLevel;
  origin: CommercialDiagnosticOrigin;
  resourceId?: string | null;
  routeId?: string | null;
  sourceRefs?: readonly string[];
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function machineParts(raw: string): { code: string | null; detail: string; tokens: string[] } {
  const text = String(raw ?? "").trim();
  if (!text) return { code: null, detail: "", tokens: [] };
  const parts = text.split(":").map((part) => part.trim()).filter(Boolean);
  const code = parts[0] && /^[A-Z][A-Z0-9_]*$/.test(parts[0]) ? parts[0] : null;
  return {
    code,
    detail: code ? parts.slice(1).join(": ") : text,
    tokens: code ? parts.slice(1) : [],
  };
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function buildCommercialDiagnostics({
  poolInputBlockers,
  options,
  optimizer,
  recommendation,
}: BuildCommercialDiagnosticsInput): CommercialDiagnosticItem[] {
  const seeds: DiagnosticSeed[] = [];
  const pushAll = (
    values: readonly string[] | null | undefined,
    level: CommercialDiagnosticLevel,
    origin: CommercialDiagnosticOrigin,
    extra: Omit<DiagnosticSeed, "raw" | "level" | "origin"> = {},
  ) => {
    for (const raw of values ?? []) {
      if (String(raw).trim()) seeds.push({ raw, level, origin, ...extra });
    }
  };

  pushAll(poolInputBlockers, "blocker", "preflight");
  pushAll(options?.blockers, "blocker", "pool_options");
  pushAll(options?.warnings, "warning", "pool_options");
  pushAll(optimizer?.missing_inputs, "missing_input", "optimizer", {
    sourceRefs: optimizer?.source_refs ?? [],
  });
  pushAll(optimizer?.warnings, "warning", "optimizer", {
    sourceRefs: optimizer?.source_refs ?? [],
  });
  for (const allocation of optimizer?.allocations ?? []) {
    pushAll(allocation.warnings, "warning", "allocation", {
      resourceId: allocation.resource_id,
      routeId: allocation.option_id,
      sourceRefs: optimizer?.source_refs ?? [],
    });
  }
  pushAll(recommendation?.warnings, "warning", "route_recommendation");
  for (const excluded of recommendation?.excluded_routes ?? []) {
    const routeId = stringValue(excluded.route_id);
    pushAll(stringArray(excluded.blockers), "blocker", "route_exclusion", { routeId });
  }

  const resources = new Map(
    (options?.portfolio_resources ?? []).map((resource) => [resource.resource_id, resource]),
  );
  const saleOptions = new Map(
    (options?.sale_options ?? []).map((option) => [option.option_id, option]),
  );

  const merged = new Map<string, CommercialDiagnosticItem>();
  for (const seed of seeds) {
    const parsed = machineParts(seed.raw);
    const tokenSet = new Set(parsed.tokens);
    const resourceId =
      seed.resourceId ??
      [...resources.keys()].find((id) => tokenSet.has(id)) ??
      null;
    const routeId =
      seed.routeId ??
      [...saleOptions.keys()].find((id) => tokenSet.has(id)) ??
      null;
    const resource = resourceId ? resources.get(resourceId) : undefined;
    const option = routeId ? saleOptions.get(routeId) : undefined;
    const sourceRefs = unique([
      ...(seed.sourceRefs ?? []),
      ...(resource?.source_refs ?? []),
      ...(option?.source_refs ?? []),
    ]);
    const key = [seed.level, seed.raw, resourceId ?? "", routeId ?? ""].join("|");
    const current = merged.get(key);
    if (current) {
      current.origins = unique([...current.origins, seed.origin]) as CommercialDiagnosticOrigin[];
      current.sourceRefs = unique([...current.sourceRefs, ...sourceRefs]);
      continue;
    }
    merged.set(key, {
      raw: seed.raw,
      code: parsed.code,
      detail: parsed.detail,
      level: seed.level,
      origins: [seed.origin],
      affectedResourceId: resourceId,
      affectedRouteId: routeId,
      sourceSystem: option?.sale_price_source_system ?? null,
      sourceReference: option?.sale_price_source_reference ?? null,
      observedAtUtc: option?.sale_price_observed_at_utc ?? null,
      freshness: option?.sale_price_freshness ?? null,
      simulated: option?.sale_price_simulated ?? null,
      sourceRefs,
    });
  }
  return [...merged.values()];
}
