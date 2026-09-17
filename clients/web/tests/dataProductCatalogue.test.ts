/**
 * Data Product catalogue reading tests (Architecture V2 Wave 4, client half).
 *
 * `07_DATA_PLATFORM.md` section 3 states the catalogue's honesty rules as contract: a product
 * the caller is not entitled to is reported restricted with **no provenance block** - never
 * omitted and never rendered as a measured zero - and a deployment without a runtime database
 * reports `UNKNOWN` freshness rather than inventing one. The client had no consumer for the
 * catalogue at all, so these tests pin the reading half of those rules: three provenance states
 * kept apart, no stand-in zeros, unknown vocabulary shown as its own code, and a surface that
 * reports a failed read instead of an empty catalogue.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  dataProductAvailabilityKey,
  dataProductFreshnessKey,
  dataProductRows,
  dataProductSummary,
  dataProductTimeBasisKey,
} from "../src/app/model/dataProductModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function product(overrides: Record<string, unknown> = {}) {
  return {
    product_id: "market-prices",
    business_name: "Market prices",
    description: "Normalised market observations",
    domain: "market",
    availability: { state: "available", note: "producer implemented" },
    time_basis: { basis: "as_of_instant", gas_day_calendar: null, freshness_expectation_minutes: 15 },
    source_families: ["EEX"],
    simulated_families: [],
    entitlement_families: ["EEX"],
    served_by: [{ kind: "endpoint", reference: "/api/market/observations", description: "" }],
    provenance_tables: ["market_observations"],
    restricted: false,
    entitlement: {
      status: "allowed",
      reason: "entitled",
      required_family_count: 1,
      granted_family_count: 1,
      restricted_family_count: 0,
      note: "",
    },
    provenance: {
      as_of_utc: "2026-02-01T09:00:00Z",
      row_count: 12,
      freshness: { status: "FRESH", expectation_minutes: 15, last_observed_at_utc: "2026-02-01T09:00:00Z" },
      confidence: "HIGH",
      quality_flags: [],
    },
    human_review_required: true,
    ...overrides,
  };
}

function catalogue(products: Array<ReturnType<typeof product>>, runtimeAvailable = true) {
  const restricted = products.filter((entry) => entry.restricted).length;
  return {
    catalogue_version: "catalogue/v1",
    generated_at_utc: "2026-02-01T09:00:00Z",
    runtime_available: runtimeAvailable,
    products,
    entitlement_summary: {
      total_products: products.length,
      allowed_products: products.length - restricted,
      restricted_products: restricted,
    },
  } as unknown as Parameters<typeof dataProductRows>[0];
}

test("an entitled product reports the provenance the backend measured", () => {
  const [row] = dataProductRows(catalogue([product()]));

  assert.equal(row.provenanceState, "measured");
  assert.equal(row.rowCount, 12);
  assert.equal(row.freshnessStatus, "FRESH");
  assert.equal(row.confidence, "HIGH");
  assert.deepEqual(row.qualityFlags, []);
  assert.equal(row.availabilityState, "available");
  assert.deepEqual(row.servedBy, ["/api/market/observations"]);
});

test("a restricted product is listed, and its provenance is withheld rather than zeroed", () => {
  const restricted = product({
    product_id: "licensed-curves",
    restricted: true,
    entitlement: {
      status: "restricted",
      reason: "entitlement_family_missing",
      required_family_count: 2,
      granted_family_count: 1,
      restricted_family_count: 1,
      note: "",
    },
    provenance: null,
  });
  const [row] = dataProductRows(catalogue([restricted]));

  // The declared facts stay: they are contract, not data.
  assert.equal(row.productId, "licensed-curves");
  assert.equal(row.availabilityState, "available");
  assert.equal(row.provenanceState, "restricted");
  // ...and nothing measured is claimed in its place.
  assert.equal(row.rowCount, null);
  assert.equal(row.freshnessStatus, null);
  assert.equal(row.confidence, null);
  assert.equal(row.entitlementReason, "entitlement_family_missing");
  assert.equal(row.restrictedFamilyCount, 1);
});

test("an entitled product with nothing measured is unmeasured, not empty", () => {
  // A deployment without a runtime database serves the declared contract and no provenance.
  const [row] = dataProductRows(catalogue([product({ provenance: null })], false));

  assert.equal(row.provenanceState, "unmeasured");
  assert.equal(row.rowCount, null);
  assert.notEqual(row.provenanceState, "measured");
});

test("a genuinely measured zero is kept as a zero, because that one is a measurement", () => {
  const empty = product({
    provenance: {
      as_of_utc: null,
      row_count: 0,
      freshness: { status: "MISSING", expectation_minutes: 15, last_observed_at_utc: null },
      confidence: "UNKNOWN",
      quality_flags: ["NO_ROWS_OBSERVED"],
    },
  });
  const [row] = dataProductRows(catalogue([empty]));

  assert.equal(row.provenanceState, "measured");
  assert.equal(row.rowCount, 0);
  assert.equal(row.freshnessStatus, "MISSING");
  assert.deepEqual(row.qualityFlags, ["NO_ROWS_OBSERVED"]);
});

test("the summary counts come from the catalogue, and say whether provenance was readable", () => {
  const entries = catalogue(
    [product(), product({ product_id: "licensed-curves", restricted: true, provenance: null })],
    false,
  );

  assert.deepEqual(dataProductSummary(entries), {
    total: 2,
    allowed: 1,
    restricted: 1,
    runtimeAvailable: false,
    generatedAtUtc: "2026-02-01T09:00:00Z",
    catalogueVersion: "catalogue/v1",
  });
  // Nothing read yet is nothing claimed: no counts are invented.
  assert.deepEqual(dataProductRows(null), []);
  assert.equal(dataProductSummary(undefined).total, 0);
});

test("a state this build has no label for is shown as its own code", () => {
  // The vocabulary is controlled, but rendering an unknown value as though it had a label
  // would be a lie about what the platform said.
  assert.equal(dataProductAvailabilityKey("available"), "data_product.availability.available");
  assert.equal(dataProductAvailabilityKey("brand_new_state"), "brand_new_state");
  assert.equal(dataProductTimeBasisKey("gas_day"), "data_product.time_basis.gas_day");
  assert.equal(dataProductTimeBasisKey("brand_new_basis"), "brand_new_basis");
  assert.equal(dataProductFreshnessKey("FRESH"), "data_product.freshness.fresh");
  assert.equal(dataProductFreshnessKey("UNRECOGNISED"), "UNRECOGNISED");
});

test("the surface reads the catalogue and reports a failure instead of an empty one", () => {
  const client = readWebSource("api/client.ts");
  const panel = readWebSource("components/DataProductCatalogue.tsx");
  const research = readWebSource("components/ResearchDataWorkspace.tsx");

  assert.match(
    client,
    /dataProducts: \(options\?: ApiRequestOptions\) =>\s*get<DataProductCatalogueDTO>\("\/data-products", undefined, options\)/s,
  );
  assert.match(client, /export interface DataProductDTO \{/);
  assert.match(client, /provenance: \{[\s\S]*?\} \| null;/);

  // The three provenance states are rendered apart, and a failed read is an alert.
  assert.match(panel, /if \(row\.provenanceState === "restricted"\) return t\("data_product\.provenance\.restricted"\);/);
  assert.match(panel, /if \(row\.provenanceState === "unmeasured"\) return t\("data_product\.provenance\.unmeasured"\);/);
  assert.match(panel, /errorText && \(\s*<div className="research-catalog-error" role="alert">/s);
  assert.match(panel, /const response = await api\.dataProducts\(\);/);
  assert.equal(panel.includes("fetch("), false);

  // It is a view of the existing research surface, not a new page (V2 04 rule 9).
  assert.match(research, /type ResearchViewId = "datasets" \| "products" \| "features" \| "targets";/);
  assert.match(research, /\{activeView === "products" && <DataProductCatalogue t=\{t\} \/>\}/);
  assert.match(research, /activeView !== "datasets" && activeView !== "products"/);
});

test("every catalogue string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = Object.keys(en).filter((key) => key.startsWith("data_product."));
  // The surface's vocabulary is enumerated from the locale itself, so a key added to one
  // locale and not the other cannot hide.
  assert.ok(keys.length >= 30, `only ${keys.length} catalogue keys were found`);
  assert.deepEqual(
    Object.keys(zh).filter((key) => key.startsWith("data_product.")).sort(),
    [...keys].sort(),
  );
  for (const key of keys) {
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
  assert.ok(en["research.tab.products"]);
  assert.ok(zh["research.tab.products"]);
});
