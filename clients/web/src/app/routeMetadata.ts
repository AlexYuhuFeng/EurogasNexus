import type { EdgeDTO } from "@/api/client";

export function normalizePointName(value: string | null | undefined): string {
  return (value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

export function metadataText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function routeLegLabel(leg: Record<string, unknown>, index: number): string {
  for (const key of ["point_name", "market_area", "hub_binding", "tso", "leg_id"]) {
    const value = metadataText(leg[key]);
    if (value) return value;
  }
  return `leg ${index + 1}`;
}

export function routeEdgeRouteId(edge: EdgeDTO): string | null {
  return metadataText(edge.metadata_json?.route_id) ?? edge.source_record_id ?? null;
}

export function routeEdgeMetadataText(edge: EdgeDTO, key: string): string | null {
  return metadataText(edge.metadata_json?.[key]);
}
