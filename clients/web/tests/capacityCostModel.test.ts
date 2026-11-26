/**
 * TAR-2 view logic: capacity cost layers (contracted, public final or indicative, not held —
 * never zero), sources in the order in force with the one used marked, and one tariff year's
 * two versions side by side. Made-up figures.
 */
import assert from "node:assert/strict";
import test from "node:test";

import type { CapacityCostLayerDTO, TariffVersionDTO, TariffYearDTO } from "../src/api/client.ts";
import {
  costHeadline,
  costText,
  fxText,
  layerReference,
  layerStatus,
  layerTone,
  orderOrigin,
  orderedYears,
  sourceSteps,
  yearCells,
} from "../src/app/model/capacityCostModel.ts";

function layer(changes: Partial<CapacityCostLayerDTO>): CapacityCostLayerDTO {
  return {
    layer: "public",
    reference: "tv-1",
    quantity: 1240,
    unit: "MWh",
    unit_cost: 0.570833,
    cost: 707.83,
    currency: "EUR",
    status: "FINAL",
    ...changes,
  };
}

test("layers read contracted, public final, public indicative and not held", () => {
  assert.equal(layerStatus(layer({ layer: "contracted", status: "CONTRACTED" })), "contracted");
  assert.equal(layerStatus(layer({})), "final");
  assert.equal(layerStatus(layer({ status: "INDICATIVE" })), "indicative");
  assert.equal(layerStatus(layer({ layer: "not_held", status: undefined as unknown as string })), "not_held");
  assert.equal(layerTone(layer({ status: "INDICATIVE" })), "watch");
  assert.equal(layerTone(layer({ layer: "not_held" })), "breach");
});

test("a cost that is not given is never shown as zero", () => {
  assert.equal(costText(null, "EUR"), null);
  assert.equal(costText(0, "EUR"), "0.00 EUR");
  assert.equal(costText(1482.83, "EUR"), "1,482.83 EUR");
  assert.equal(costHeadline({ complete: false, indicative: false, total_cost: null }), "incomplete");
  assert.equal(costHeadline({ complete: true, indicative: true, total_cost: 10 }), "complete_indicative");
  assert.equal(costHeadline({ complete: true, indicative: false, total_cost: 10 }), "complete_final");
});

test("an FX rate reads as one unit of the base currency, or not at all", () => {
  assert.equal(fxText({ value: 1 / 1.1, from: "USD", to: "EUR" }), "1 USD = 0.909091 EUR");
  assert.equal(fxText({ value: null, from: "USD", to: "EUR" }), null);
});

test("a layer names its booking or its tariff year and how the rest is bought", () => {
  assert.equal(
    layerReference(layer({ layer: "contracted", booking_id: "ENDUR:LT-7", acquired_via: "long_term", contracted_price: "3.65 EUR/(kWh/h)/y" })),
    "ENDUR:LT-7 · long_term · 3.65 EUR/(kWh/h)/y",
  );
  assert.equal(
    layerReference(layer({ tariff_year: "GY 2026/27", public_price: "0.0125 EUR/(kWh/h)/d", how_bought: "day-ahead auction reserve price" })),
    "GY 2026/27 · 0.0125 EUR/(kWh/h)/d · day-ahead auction reserve price",
  );
});

test("sources keep the order in force, numbered, with the used ones marked", () => {
  const steps = sourceSteps([
    { tier: "contracted_bank", label: "bank", used: false, reason: "not_configured", note: "none" },
    { tier: "published_reference", label: "fixing", used: false, reason: "not_entitled", note: null },
    { tier: "ecb_reference", label: "ECB", used: true, reason: "used", note: null },
  ]);
  assert.deepEqual(
    steps.map((step) => [step.position, step.tier, step.used, step.reason]),
    [
      [1, "contracted_bank", false, "not_configured"],
      [2, "published_reference", false, "not_entitled"],
      [3, "ecb_reference", true, "used"],
    ],
  );
  assert.deepEqual(orderOrigin("default"), { key: "default", setting: null });
  assert.deepEqual(orderOrigin("setting:fx_rate@lng_demurrage"), { key: "setting", setting: "fx_rate@lng_demurrage" });
  assert.deepEqual(orderOrigin("calculation"), { key: "calculation", setting: null });
});

function version(status: "INDICATIVE" | "FINAL", published: string | null): TariffVersionDTO {
  return {
    tariff_key: `k-${status}`,
    version: status === "FINAL" ? 2 : 1,
    version_id: `tv-${status}`,
    change_kind: status === "FINAL" ? "status_change" : "first",
    status,
    status_basis: status === "FINAL" ? "operator_stated" : "nc_tar_before_yearly_auction",
    status_change: null,
    data_class: "sourced",
    publisher_id: "p",
    publisher_name: "P",
    facility_kind: "point",
    facility_id: "ITP-1",
    facility_name: "Point one",
    operator: "Operator A",
    country: "XX",
    market_area: null,
    direction: "EXIT",
    product: "ANNUAL",
    duration: "yearly",
    firmness: "FIRM",
    value: status === "FINAL" ? 4.2 : 4,
    by_class: null,
    unit: "EUR/(kWh/h)/y",
    currency: "EUR",
    period_from: "2027-10-01",
    period_to: "2028-09-30",
    published_at_utc: published,
    retrieved_at_utc: "2027-06-01T09:00:00+00:00",
    recorded_at_utc: "2027-06-01T09:00:00+00:00",
    superseded_at_utc: null,
    source_url: "https://publisher.example/t",
    source_ref: "",
    content_hash: "x",
    event_id: null,
    withdrawn: false,
    tariff_year: "GY 2027/28",
    new: status === "FINAL",
  };
}

function year(label: string, first: string, used: "INDICATIVE" | "FINAL" | null): TariffYearDTO {
  return {
    tariff_year: { label, convention: "gas_year", first_gas_day: first, last_gas_day: first },
    direction: "EXIT",
    product: "ANNUAL",
    firmness: "FIRM",
    operator: "Operator A",
    period_from: first,
    period_to: null,
    INDICATIVE: version("INDICATIVE", "2027-04-30T00:00:00+00:00"),
    FINAL: used === "FINAL" ? version("FINAL", null) : null,
    versions: used === "FINAL" ? 2 : 1,
    used,
    used_version_id: null,
  };
}

test("a tariff year shows both versions side by side, the one used marked", () => {
  const [indicative, final] = yearCells(year("GY 2027/28", "2027-10-01", "FINAL"));
  assert.equal(indicative.held && !indicative.used, true);
  assert.equal(indicative.published, "2027-04-30T00:00:00+00:00");
  assert.equal(final.used && final.isNew, true);
  // No publication date stated: none is invented; the record time stands beside it.
  assert.equal(final.published, null);
  assert.equal(final.recorded, "2027-06-01T09:00:00+00:00");
  const [, missing] = yearCells(year("GY 2028/29", "2028-10-01", "INDICATIVE"));
  assert.equal(missing.held, false);
  assert.equal(missing.figure, "—");
  assert.deepEqual(
    orderedYears([year("GY 2026/27", "2026-10-01", "FINAL"), year("GY 2027/28", "2027-10-01", "INDICATIVE")]).map(
      (item) => item.tariff_year.label,
    ),
    ["GY 2027/28", "GY 2026/27"],
  );
});
