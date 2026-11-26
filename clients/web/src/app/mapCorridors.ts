import type { EdgeDTO, MapPointFlowDTO, NodeDTO } from "@/api/client";
import { presentationPath } from "./mapLineGeometry.ts";

/**
 * The main import corridors (Norway, North Africa, TAP, TurkStream; Nord Stream out of service),
 * read as supply corridors: one line from outside Europe to its entry point, with the flow
 * measured at that entry point (owner, 2026-11-26).
 *
 * The topology follow-up adds them as edges. This reads any edge that says it is one, in the
 * shapes the reference bundle uses: `edge_type` "import_corridor" or "supply_corridor", or
 * `metadata.corridor` / `metadata.supply_corridor` true. Optional metadata: `corridor_name`
 * (else the edge's `name`), `in_service` false or `status` "out_of_service" (drawn as out of
 * service, never with a flow), `presentation_path` for the drawn path (else from-to). The entry
 * point is the edge's `to_node_id` (or `metadata.entry_node_id`). The flow is the latest
 * measured entry flow at that point, summed over its operators; none measured, none shown.
 */

export interface SupplyCorridor {
  id: string;
  name: string;
  coordinates: Array<[number, number]>;
  entryNodeId: string;
  inService: boolean;
  /** GWh/d measured at the entry point, or null when none is measured. */
  entryGwhD: number | null;
  /** Where the corridor's label sits: the entry point. */
  labelAt: [number, number];
}

export function isSupplyCorridor(edge: Pick<EdgeDTO, "edge_type" | "metadata_json">): boolean {
  const meta = edge.metadata_json ?? {};
  return edge.edge_type === "import_corridor" || edge.edge_type === "supply_corridor"
    || meta.corridor === true || meta.supply_corridor === true;
}

export function supplyCorridors(
  edges: readonly EdgeDTO[],
  nodes: readonly NodeDTO[],
  flows: readonly MapPointFlowDTO[],
): SupplyCorridor[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const out: SupplyCorridor[] = [];
  for (const edge of edges) {
    if (!isSupplyCorridor(edge)) continue;
    const meta = edge.metadata_json ?? {};
    const entryNodeId = typeof meta.entry_node_id === "string" ? meta.entry_node_id : edge.to_node_id;
    const from = byId.get(edge.from_node_id);
    const entry = byId.get(entryNodeId) ?? byId.get(edge.to_node_id);
    const path = presentationPath(edge)
      ?? (from && entry && [from.lon, from.lat, entry.lon, entry.lat].every(Number.isFinite)
        ? [[from.lon, from.lat], [entry.lon, entry.lat]] as Array<[number, number]>
        : null);
    if (!path || !entry) continue;
    const inService = meta.in_service !== false && meta.status !== "out_of_service";
    const measured = flows.filter((flow) => flow.direction === "entry" && flow.gwh_d != null
      && (flow.location.ref_id === entry.id || flow.point_id === entry.id));
    const entryGwhD = inService && measured.length ? measured.reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) : null;
    const name = [meta.corridor_name, meta.name, edge.id].find((value) => typeof value === "string" && value.trim()) as string;
    out.push({ id: edge.id, name, coordinates: path, entryNodeId: entry.id, inService, entryGwhD, labelAt: [entry.lon, entry.lat] });
  }
  return out;
}

/** "Langeled · 61 GWh/d", "Nord Stream · out of service", or the name alone. */
export function corridorLabel(corridor: SupplyCorridor, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (!corridor.inService) return `${corridor.name} · ${t("map.corridor.out_of_service")}`;
  if (corridor.entryGwhD === null) return corridor.name;
  return `${corridor.name} · ${Math.round(corridor.entryGwhD).toLocaleString("en-GB")} GWh/d`;
}
