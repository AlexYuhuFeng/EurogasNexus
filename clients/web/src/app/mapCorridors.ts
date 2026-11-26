import type { SupplyCorridorDTO } from "@/api/client";

/**
 * Europe's main import supply corridors (GET /api/reference-network/supply-corridors): the big
 * picture of where Europe's gas comes from, one layer on by default.
 *
 * - The line is thin: solid where its path follows SciGRID_gas, dashed where it is a schematic
 *   straight line.
 * - In service: width by the latest flow in GWh/d (the map's flow encoding) and an arrowhead at
 *   the landing. Out of service: grey, no arrow.
 * - The label at the landing: the corridor's name and its flow, "out of service since 2022", or
 *   "not published" when no flow is stored (null is unknown, never zero).
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface CorridorLine {
  id: string;
  coordinates: Array<[number, number]>;
  schematic: boolean;
  inService: boolean;
  /** Line width in px: 1.2 out of service; in service 1.5 to 5 by the square root of the flow. */
  width: number;
  /** Where the label and the arrowhead sit: the first landing point (else the line's end). */
  landing: [number, number];
}

export function corridorWidth(flowGwhD: number | null, largest: number, inService: boolean): number {
  if (!inService || flowGwhD === null || !(largest > 0) || !(flowGwhD > 0)) return inService ? 1.5 : 1.2;
  return Math.round((1.5 + 3.5 * Math.sqrt(flowGwhD / largest)) * 10) / 10;
}

export function corridorLines(corridors: readonly SupplyCorridorDTO[]): CorridorLine[] {
  const largest = Math.max(0, ...corridors.map((item) => (item.status === "in_service" ? item.latest_flow_gwh_d ?? 0 : 0)));
  return corridors
    .filter((item) => (item.geometry?.coordinates?.length ?? 0) > 1)
    .map((item) => {
      const coordinates = item.geometry.coordinates;
      const first = item.landing_points[0];
      const inService = item.status === "in_service";
      return {
        id: item.id,
        coordinates,
        schematic: item.geometry.basis === "schematic",
        inService,
        width: corridorWidth(item.latest_flow_gwh_d, largest, inService),
        landing: first ? [first.lon, first.lat] : coordinates[coordinates.length - 1],
      };
    });
}

/**
 * "Langeled · 61 GWh/d", "Nord Stream 1 · out of service since 2022", "Norpipe · not published".
 * A shared entry point carries no figure on the map: the point's flow is not the corridor's.
 */
export function corridorLabel(corridor: SupplyCorridorDTO, t: Translate): string {
  if (corridor.status === "out_of_service") {
    return `${corridor.name} · ${corridor.since ? t("map.corridor.out_since", { year: corridor.since.slice(0, 4) }) : t("map.corridor.out_of_service")}`;
  }
  if (corridor.latest_flow_gwh_d === null) return `${corridor.name} · ${t("map.corridor.not_published")}`;
  if (corridor.shared_entry_point) return `${corridor.name} · ${t("map.corridor.shared")}`;
  return `${corridor.name} · ${Math.round(corridor.latest_flow_gwh_d).toLocaleString("en-GB")} GWh/d`;
}

/**
 * The side panel's latest-flow line. At a shared entry point it names the point and says so,
 * so the point's whole flow is never read as the corridor's own.
 */
export function corridorFlowText(corridor: SupplyCorridorDTO, t: Translate): string {
  if (corridor.latest_flow_gwh_d === null) return t("map.corridor.not_published");
  const flow = `${Math.round(corridor.latest_flow_gwh_d).toLocaleString("en-GB")} GWh/d`;
  if (!corridor.shared_entry_point) return flow;
  const point = corridor.landing_points[0]?.name ?? "–";
  return t("map.corridor.card.shared_flow", { point, flow });
}

/** The newest gas day among the corridor's stored flows, or null. */
export function corridorFlowDay(corridor: SupplyCorridorDTO): string | null {
  const days = corridor.flow_series
    .map((item) => item.latest_flow?.gas_day_start_utc?.slice(0, 10) ?? null)
    .filter((day): day is string => Boolean(day))
    .sort();
  return days[days.length - 1] ?? null;
}
