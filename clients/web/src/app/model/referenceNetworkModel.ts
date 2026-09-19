/**
 * The reference-network catalogue: facilities and market hubs (slice D of the D3 decision).
 *
 * `GET /api/reference-network/facilities` and `GET /api/reference-network/market-hubs` declare the
 * physical and commercial register the map's topology is drawn against - which facilities exist,
 * of what kind, in which country, with what declared capacity, and which market hubs the
 * deployment recognises - and neither had a consumer. The map renders nodes and edges it can
 * place; the register is what makes those placements checkable, and it is the only list that
 * includes what the map does not draw.
 *
 * The rows carry no arithmetic: a declared capacity that is absent stays absent (the route's
 * `capacity_boe_d` is nullable), and nothing here sums or averages two rows into a number the
 * deployment did not state.
 */

import type { FacilityDTO, MarketHubDTO } from "@/api/client";

/** One facility, as the catalogue renders it. */
export interface FacilityRow {
  readonly id: string;
  readonly name: string;
  readonly facilityType: string;
  readonly country: string;
  /** Declared daily capacity, or null when the row declares none. Never defaulted to zero. */
  readonly capacityBoeD: number | null;
  /** The source system the row names, when it names one. */
  readonly source: string | null;
}

/** One market hub, as the catalogue renders it. */
export interface MarketHubRow {
  readonly id: string;
  readonly name: string;
  readonly hubCode: string;
  readonly country: string;
  readonly description: string | null;
}

/**
 * The facility types the deployment declares, spelled as `reference_facilities.facility_type`
 * spells them.
 *
 * The four the runtime stores today (a border point, a storage site, an LNG terminal and an entry
 * point) are said in words; a type a newer deployment declares is not blanked and not guessed at,
 * so the caller renders the deployment's own token.
 */
const FACILITY_TYPE_KEYS: Readonly<Record<string, string>> = {
  border_point: "network.facility_type.border_point",
  storage: "network.facility_type.storage",
  lng_terminal: "network.facility_type.lng_terminal",
  entry_point: "network.facility_type.entry_point",
};

/** The translation key for a declared facility type, or null when it is not one this build knows. */
export function facilityTypeKey(value: string): string | null {
  return FACILITY_TYPE_KEYS[value] ?? null;
}

/** Facility rows, ordered by name so two reads render the same way. */
export function facilityRows(facilities: readonly FacilityDTO[] | null): FacilityRow[] {
  if (!facilities) return [];
  return facilities
    .map((facility) => ({
      id: facility.id,
      name: facility.name,
      facilityType: facility.facility_type,
      country: facility.country,
      capacityBoeD: facility.capacity_boe_d ?? null,
      source: facility.source_system ?? null,
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
}

function distinctSorted(values: readonly string[]): string[] {
  return [...new Set(values.filter((value) => value.trim().length > 0))].sort();
}

/** The facility types present in a read, for the filter the route itself accepts. */
export function facilityTypeOptions(rows: readonly FacilityRow[]): string[] {
  return distinctSorted(rows.map((row) => row.facilityType));
}

/** The countries present in a read, for the filter the route itself accepts. */
export function facilityCountryOptions(rows: readonly FacilityRow[]): string[] {
  return distinctSorted(rows.map((row) => row.country));
}

/** Market-hub rows, ordered by name. */
export function marketHubRows(hubs: readonly MarketHubDTO[] | null): MarketHubRow[] {
  if (!hubs) return [];
  return hubs
    .map((hub) => ({
      id: hub.id,
      name: hub.name,
      hubCode: hub.hub_code,
      country: hub.country,
      description: hub.description ?? null,
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
}

/** How many rows declare a capacity and how many do not, so "no capacity declared" is visible. */
export function declaredCapacityCounts(rows: readonly FacilityRow[]): {
  declared: number;
  undeclared: number;
} {
  const declared = rows.filter((row) => row.capacityBoeD !== null).length;
  return { declared, undeclared: rows.length - declared };
}
