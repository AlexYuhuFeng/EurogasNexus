/**
 * The capacity profile book (slice D of the D3 decision).
 *
 * `GET /api/contracts/capacity` publishes the capacity profiles the runtime stores - one row per
 * point, with the capacity, the unit the row declares, the window it is valid for, the firmness
 * and the source reference. No surface read it, so the declared capacity behind the operating
 * board was invisible: the board shows what flowed and what is technically available, never what
 * the operator has actually booked.
 *
 * Two things this module refuses to do:
 *
 * - it does not sum capacities. The rows are separate windows over the same points, so a total
 *   would be a number the deployment never stated; and
 * - it does not decide which rows are "current". The envelope carries no server as-of instant, so
 *   a window classified against the client's own clock would be the client's opinion. The window
 *   is rendered as declared, and that is all the read established.
 *
 * The payload's field is named `capacity_boe_d` while the row's own `unit` says MWh/d: the unit the
 * row declares is what the surface renders, because the unit is the explicit statement and the
 * field name is legacy.
 */

import type { CapacityContractDTO } from "@/api/client";

/** One capacity profile, as the book renders it. */
export interface CapacityContractRow {
  readonly contractId: string;
  /** The point the profile belongs to (`route_name` carries the point's name). */
  readonly pointName: string;
  readonly capacity: number;
  /** The unit the row declares, rendered verbatim rather than assumed from the field name. */
  readonly unit: string;
  readonly validFrom: string;
  readonly validTo: string;
  /** The row's firmness, as the runtime stores it. */
  readonly firmness: string;
}

/**
 * Capacity-profile rows in the order the route returns them (newest window first).
 *
 * The route already orders by the window's start, descending, and it owns that order: re-sorting
 * here would be a second opinion about which profile is newest.
 */
export function capacityContractRows(
  contracts: readonly CapacityContractDTO[] | null,
): CapacityContractRow[] {
  if (!contracts) return [];
  return contracts.map((contract) => ({
    contractId: contract.contract_id,
    pointName: contract.route_name,
    capacity: contract.capacity_boe_d,
    unit: contract.unit,
    validFrom: contract.start_utc,
    validTo: contract.end_utc,
    firmness: contract.status,
  }));
}

/**
 * The firmness values present in a read, so the book can say which postures it holds.
 *
 * Undeclared values are returned as they are: a firmness this build does not know is a fact about
 * the deployment, not a row to hide.
 */
export function firmnessOptions(rows: readonly CapacityContractRow[]): string[] {
  return [...new Set(rows.map((row) => row.firmness).filter((value) => value.trim().length > 0))].sort();
}

/** How many distinct points the book covers, which is a count and not a sum. */
export function coveredPointCount(rows: readonly CapacityContractRow[]): number {
  return new Set(rows.map((row) => row.pointName)).size;
}
