/**
 * Data Product catalogue reading model (Architecture V2 Wave 4, client half).
 *
 * `07_DATA_PLATFORM.md` section 3 declares a catalogue that says what a product *is* and how
 * much of it exists today, with the honesty rules stated as contract: a product whose required
 * source family the caller is not entitled to is reported `restricted` with **no provenance
 * block** - never omitted, never rendered as a measured zero - and a deployment without a
 * runtime database reports freshness as `UNKNOWN` rather than inventing one.
 *
 * The client had no consumer for that catalogue at all, so those rules had no surface to be
 * true on. This module is the reading half: it turns entries into rows a surface can render,
 * keeping three provenance states apart instead of collapsing them into "0 rows":
 *
 * - `measured` - the backend measured it; the numbers are the backend's;
 * - `restricted` - this caller is not entitled; the backend withheld the block on purpose;
 * - `unmeasured` - the caller is entitled but nothing was measured (no runtime database).
 */

import type { DataProductCatalogueDTO, DataProductDTO } from "../../api/client.ts";

/** How a row's provenance stands, kept apart rather than collapsed into one empty state. */
export type DataProductProvenanceState = "measured" | "restricted" | "unmeasured";

export interface DataProductRow {
  readonly productId: string;
  readonly businessName: string;
  readonly description: string;
  readonly domain: string;
  /** The declared availability state, exactly as the catalogue reported it. */
  readonly availabilityState: string;
  readonly availabilityNote: string;
  readonly timeBasis: string;
  readonly gasDayCalendar: string | null;
  readonly freshnessExpectationMinutes: number | null;
  readonly sourceFamilies: readonly string[];
  readonly simulatedFamilies: readonly string[];
  readonly servedBy: readonly string[];
  readonly provenanceState: DataProductProvenanceState;
  /** Measured rows, or `null` when there is nothing measured to show. Never a stand-in zero. */
  readonly rowCount: number | null;
  readonly freshnessStatus: string | null;
  readonly confidence: string | null;
  readonly qualityFlags: readonly string[];
  readonly entitlementReason: string;
  readonly restrictedFamilyCount: number;
}

/**
 * One row per catalogue entry, in the order the catalogue declared.
 *
 * A restricted product keeps its declared facts - name, case, time basis, sources - because
 * those are contract, not data; only its provenance is withheld.
 */
export function dataProductRows(
  catalogue: DataProductCatalogueDTO | null | undefined,
): DataProductRow[] {
  return (catalogue?.products ?? []).map(dataProductRow);
}

export function dataProductRow(product: DataProductDTO): DataProductRow {
  const provenance = product.provenance;
  const provenanceState: DataProductProvenanceState = product.restricted
    ? "restricted"
    : provenance
      ? "measured"
      : "unmeasured";
  return {
    productId: product.product_id,
    businessName: product.business_name,
    description: product.description,
    domain: product.domain,
    availabilityState: product.availability.state,
    availabilityNote: product.availability.note,
    timeBasis: product.time_basis.basis,
    gasDayCalendar: product.time_basis.gas_day_calendar,
    freshnessExpectationMinutes: product.time_basis.freshness_expectation_minutes,
    sourceFamilies: product.source_families,
    simulatedFamilies: product.simulated_families,
    servedBy: product.served_by.map((surface) => surface.reference),
    provenanceState,
    // Only a measured provenance block carries a count. A withheld or unmeasured one carries
    // none, so the surface cannot print a zero that reads like "this product is empty".
    rowCount: provenanceState === "measured" ? provenance?.row_count ?? 0 : null,
    freshnessStatus: provenanceState === "measured" ? provenance?.freshness.status ?? null : null,
    confidence: provenanceState === "measured" ? provenance?.confidence ?? null : null,
    qualityFlags: provenanceState === "measured" ? provenance?.quality_flags ?? [] : [],
    entitlementReason: product.entitlement.reason,
    restrictedFamilyCount: product.entitlement.restricted_family_count,
  };
}

/** The catalogue's own counts, plus whether its provenance read was available at all. */
export interface DataProductSummary {
  readonly total: number;
  readonly allowed: number;
  readonly restricted: number;
  /** False when the deployment served the declared contract without runtime provenance. */
  readonly runtimeAvailable: boolean;
  readonly generatedAtUtc: string | null;
  readonly catalogueVersion: string | null;
}

export function dataProductSummary(
  catalogue: DataProductCatalogueDTO | null | undefined,
): DataProductSummary {
  return {
    total: catalogue?.entitlement_summary.total_products ?? 0,
    allowed: catalogue?.entitlement_summary.allowed_products ?? 0,
    restricted: catalogue?.entitlement_summary.restricted_products ?? 0,
    runtimeAvailable: catalogue?.runtime_available === true,
    generatedAtUtc: catalogue?.generated_at_utc ?? null,
    catalogueVersion: catalogue?.catalogue_version ?? null,
  };
}

/**
 * Label for an availability state, as a translation key, or the raw state.
 *
 * The states are a controlled vocabulary, but a client must not render an unknown value as
 * though it had a label for it: an unrecognised state is shown as its own code, which is
 * honest and still legible to the operator who reads the catalogue.
 */
export function dataProductAvailabilityKey(state: string): string {
  const known: Record<string, string> = {
    available: "data_product.availability.available",
    operator_input_only: "data_product.availability.operator_input_only",
    simulated_only: "data_product.availability.simulated_only",
    declared_only: "data_product.availability.declared_only",
    not_implemented: "data_product.availability.not_implemented",
  };
  return known[state] ?? state;
}

/** The same rule for a time basis. */
export function dataProductTimeBasisKey(basis: string): string {
  const known: Record<string, string> = {
    as_of_instant: "data_product.time_basis.as_of_instant",
    gas_day: "data_product.time_basis.gas_day",
    delivery_period: "data_product.time_basis.delivery_period",
    contract_term: "data_product.time_basis.contract_term",
  };
  return known[basis] ?? basis;
}

/** And for a freshness status reported inside a measured provenance block. */
export function dataProductFreshnessKey(status: string): string {
  const known: Record<string, string> = {
    FRESH: "data_product.freshness.fresh",
    LATE: "data_product.freshness.late",
    STALE: "data_product.freshness.stale",
    MISSING: "data_product.freshness.missing",
    UNKNOWN: "data_product.freshness.unknown",
  };
  return known[status] ?? status;
}
