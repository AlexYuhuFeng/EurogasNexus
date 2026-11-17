/**
 * The faint trunk-line layer under the drawn connections: north-west Europe's gas
 * transmission pipes from the open SciGRID_gas IGGIELGN reference (DLR, CC BY 4.0), generalised
 * by the bundle build (`scripts/ops/build_reference_network_bundle.py --scigrid-dir`) and served
 * by the application itself (no third-party request).
 *
 * Presentation only: it shows the general direction pipes run. It is not the network the
 * product prices on (that is the ENTSOG market-area adjacency) and carries no capacity, flow
 * or tariff; nothing selects or hovers it.
 */

export const CONTEXT_PIPELINES_PATH = "map/context-pipelines.geojson";
export const CONTEXT_PIPELINES_ATTRIBUTION = "Pipelines: SciGRID_gas IGGIELGN (DLR), CC BY 4.0";

export interface ContextPipelineCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: { id: string; diameter_mm: number };
    geometry: { type: "LineString"; coordinates: Array<[number, number]> };
  }>;
}

let pending: Promise<ContextPipelineCollection | null> | null = null;

/** The layer's data, read once per page from the application's own origin; null if absent. */
export function loadContextPipelines(): Promise<ContextPipelineCollection | null> {
  if (!pending) {
    const base = (import.meta.env?.BASE_URL as string | undefined) ?? "/";
    const url = `${base.endsWith("/") ? base : `${base}/`}${CONTEXT_PIPELINES_PATH}`;
    pending = fetch(url)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => (data && Array.isArray(data.features) ? (data as ContextPipelineCollection) : null))
      .catch(() => null);
  }
  return pending;
}

/** The same lines in the map's coordinate system (a provider may need a datum shift). */
export function projectContextPipelines(
  data: ContextPipelineCollection,
  project: (lon: number, lat: number) => [number, number],
): ContextPipelineCollection {
  return {
    type: "FeatureCollection",
    features: data.features.map((feature) => ({
      ...feature,
      geometry: {
        type: "LineString",
        coordinates: feature.geometry.coordinates.map(([lon, lat]) => project(lon, lat)),
      },
    })),
  };
}
