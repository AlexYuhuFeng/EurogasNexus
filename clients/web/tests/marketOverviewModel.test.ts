import assert from "node:assert/strict";
import test from "node:test";
import type { IntradayOpportunityDTO, MarketQuoteDTO } from "../src/api/client.ts";
import {
  buildMarketOverviewComparisons,
  formatQuoteBidAsk,
  nextMarketOverviewExpiryMs,
} from "../src/app/model/marketOverviewModel.ts";

const deliveryStart = "2026-09-09T04:00:00Z";
const deliveryEnd = "2026-09-10T04:00:00Z";
const nowMs = Date.parse("2026-09-09T03:00:30Z");

function quote(overrides: Partial<MarketQuoteDTO>): MarketQuoteDTO {
  return {
    quote_id: "quote",
    source_system: "EEX",
    source_record_id: null,
    venue: "EEX",
    instrument_id: "EEX-DAY-AHEAD",
    hub: "TTF",
    product: "day-ahead",
    delivery_start_utc: deliveryStart,
    delivery_end_utc: deliveryEnd,
    bid_price: 30,
    ask_price: 32,
    last_price: 31,
    bid_quantity_mwh: 100,
    ask_quantity_mwh: 100,
    currency: "EUR",
    unit: "MWh",
    observed_at_utc: "2026-09-09T03:00:00Z",
    received_at_utc: "2026-09-09T03:00:00Z",
    source_reference: "test://quote",
    freshness: "fresh",
    quality_score: 1,
    simulated: true,
    metadata_json: { price_level: "L1" },
    ...overrides,
  };
}

function opportunity(overrides: Partial<IntradayOpportunityDTO>): IntradayOpportunityDTO {
  return {
    opportunity_id: "opportunity-1",
    scan_id: "scan-1",
    opportunity_type: "CROSS_HUB_TRANSPORT_SPREAD",
    status: "WATCH",
    buy_quote_id: "nbp-quote",
    sell_quote_id: "ttf-quote",
    route_id: "route-1",
    route_name: "NBP -> TTF",
    buy_venue: "EEX",
    sell_venue: "EEX",
    buy_hub: "NBP",
    sell_hub: "TTF",
    product: "day-ahead",
    delivery_start_utc: deliveryStart,
    delivery_end_utc: deliveryEnd,
    comparison_currency: "EUR",
    comparison_unit: "EUR/MWh",
    buy_ask: 34,
    sell_bid: 35,
    gross_spread: 1,
    route_cost: null,
    trading_cost: 0,
    risk_buffer: 0,
    net_margin: null,
    max_quantity_mwh: null,
    indicative_net_value: null,
    quote_age_seconds: 0,
    confidence_score: 1,
    cost_components: [],
    source_refs: ["test://opportunity"],
    assumptions: [],
    missing_inputs: [],
    warnings: [],
    detected_at_utc: "2026-09-09T03:00:00Z",
    valid_until_utc: "2026-09-09T03:01:00Z",
    simulated: true,
    human_review_required: true,
    ...overrides,
  };
}

test("market overview keeps true quote mids and renders the backend comparison basis", () => {
  const rows = buildMarketOverviewComparisons(
    ["TTF", "NBP"],
    [
      quote({ quote_id: "ttf-quote", hub: "TTF", bid_price: 30, ask_price: 32, last_price: 99 }),
      quote({ quote_id: "nbp-quote", hub: "NBP", bid_price: 34, ask_price: 36, last_price: 1 }),
    ],
    [opportunity({ gross_spread: 1.4 })],
    nowMs,
  );

  assert.equal(rows[0].mid, 31);
  assert.equal(rows[1].mid, 35);
  assert.equal(rows[1].spread, 1.4);
  assert.equal(rows[1].spreadUnit, "EUR/MWh");
  assert.equal(rows[1].opportunity?.opportunity_id, "opportunity-1");
  assert.match(rows[1].contextTitle, /product=day-ahead/);
  assert.match(rows[1].contextTitle, /basis=L1/);
  assert.match(rows[1].contextTitle, /spread_source=opportunity-1/);
});

test("market overview does not invent a spread or a TTF zero without a backend opportunity", () => {
  const rows = buildMarketOverviewComparisons(
    ["TTF", "NBP"],
    [
      quote({ quote_id: "ttf-quote", hub: "TTF" }),
      quote({ quote_id: "nbp-quote", hub: "NBP" }),
    ],
    [],
    nowMs,
  );

  assert.equal(rows[0].spread, null);
  assert.equal(rows[1].spread, null);
  assert.equal(rows[1].spreadUnit, null);
});

test("market overview rejects backend spreads with incompatible delivery or quote basis", () => {
  const ttf = quote({ quote_id: "ttf-quote", hub: "TTF" });
  const nbp = quote({ quote_id: "nbp-quote", hub: "NBP", metadata_json: { price_level: "L2" } });
  const rows = buildMarketOverviewComparisons(
    ["NBP"],
    [ttf, nbp],
    [opportunity({ delivery_start_utc: "2026-09-10T04:00:00Z" })],
    nowMs,
  );

  assert.equal(rows[0].spread, null);
  assert.equal(rows[0].opportunity, null);
});

test("market overview rejects a delivery mismatch independently", () => {
  const rows = buildMarketOverviewComparisons(
    ["NBP"],
    [quote({ quote_id: "ttf-quote", hub: "TTF" }), quote({ quote_id: "nbp-quote", hub: "NBP" })],
    [opportunity({ delivery_end_utc: "2026-09-11T04:00:00Z" })],
    nowMs,
  );

  assert.equal(rows[0].spread, null);
});

test("market overview rejects a basis mismatch independently", () => {
  const rows = buildMarketOverviewComparisons(
    ["NBP"],
    [
      quote({ quote_id: "ttf-quote", hub: "TTF", metadata_json: { price_level: "L1" } }),
      quote({ quote_id: "nbp-quote", hub: "NBP", metadata_json: { price_level: "L2" } }),
    ],
    [opportunity({})],
    nowMs,
  );

  assert.equal(rows[0].spread, null);
});

test("market overview does not reverse backend opportunity direction", () => {
  const rows = buildMarketOverviewComparisons(
    ["TTF", "NBP"],
    [quote({ quote_id: "ttf-quote", hub: "TTF" }), quote({ quote_id: "nbp-quote", hub: "NBP" })],
    [opportunity({ buy_hub: "TTF", sell_hub: "NBP", buy_quote_id: "ttf-quote", sell_quote_id: "nbp-quote" })],
    nowMs,
  );

  assert.equal(rows[0].spread, null);
  assert.equal(rows[1].spread, null);
});

test("market overview requires the current quote identities", () => {
  const rows = buildMarketOverviewComparisons(
    ["NBP"],
    [quote({ quote_id: "ttf-quote", hub: "TTF" }), quote({ quote_id: "nbp-quote", hub: "NBP" })],
    [opportunity({ buy_quote_id: "older-nbp-quote" })],
    nowMs,
  );

  assert.equal(rows[0].spread, null);
});

test("market overview rejects expired opportunities by time and normalized status", () => {
  const expiredByTime = buildMarketOverviewComparisons(
    ["NBP"],
    [quote({ quote_id: "ttf-quote", hub: "TTF" }), quote({ quote_id: "nbp-quote", hub: "NBP" })],
    [opportunity({ status: "WATCH", valid_until_utc: "2026-09-09T02:59:59Z" })],
    nowMs,
  );
  const expiredByStatus = buildMarketOverviewComparisons(
    ["NBP"],
    [quote({ quote_id: "ttf-quote", hub: "TTF" }), quote({ quote_id: "nbp-quote", hub: "NBP" })],
    [opportunity({ status: "expired", valid_until_utc: "2026-09-09T04:00:00Z" })],
    nowMs,
  );

  assert.equal(expiredByTime[0].spread, null);
  assert.equal(expiredByStatus[0].spread, null);
});

test("market overview leaves true mid unavailable when either quote side is absent", () => {
  const rows = buildMarketOverviewComparisons(
    ["NBP"],
    [quote({ quote_id: "nbp-quote", hub: "NBP", bid_price: null, last_price: 31 })],
    [],
    nowMs,
  );

  assert.equal(rows[0].bid, null);
  assert.equal(rows[0].mid, null);
});

test("market overview rejects missing or contradictory quote units", () => {
  const ttf = quote({ quote_id: "ttf-quote", hub: "TTF" });
  const missingUnitRows = buildMarketOverviewComparisons(
    ["NBP"],
    [ttf, quote({ quote_id: "nbp-quote", hub: "NBP", unit: "" })],
    [opportunity({})],
    nowMs,
  );
  const contradictoryUnitRows = buildMarketOverviewComparisons(
    ["NBP"],
    [ttf, quote({ quote_id: "nbp-quote", hub: "NBP", unit: "GBP/MWh" })],
    [opportunity({})],
    nowMs,
  );
  const contradictoryBackendUnitRows = buildMarketOverviewComparisons(
    ["NBP"],
    [ttf, quote({ quote_id: "nbp-quote", hub: "NBP" })],
    [opportunity({ comparison_currency: "EUR", comparison_unit: "GBP/MWh" })],
    nowMs,
  );

  assert.equal(missingUnitRows[0].spread, null);
  assert.equal(contradictoryUnitRows[0].spread, null);
  assert.equal(contradictoryUnitRows[0].priceUnit, null);
  assert.equal(contradictoryBackendUnitRows[0].spread, null);
});

test("market overview accepts a differing native currency only from a known backend basis", () => {
  const rows = buildMarketOverviewComparisons(
    ["NBP"],
    [
      quote({ quote_id: "ttf-quote", hub: "TTF", currency: "EUR" }),
      quote({ quote_id: "nbp-quote", hub: "NBP", currency: "GBP" }),
    ],
    [opportunity({ comparison_currency: "EUR", comparison_unit: "EUR/MWh", gross_spread: 2.5 })],
    nowMs,
  );
  const noBackendRows = buildMarketOverviewComparisons(
    ["NBP"],
    [
      quote({ quote_id: "ttf-quote", hub: "TTF", currency: "EUR" }),
      quote({ quote_id: "nbp-quote", hub: "NBP", currency: "GBP" }),
    ],
    [],
    nowMs,
  );

  assert.equal(rows[0].spread, 2.5);
  assert.equal(rows[0].spreadUnit, "EUR/MWh");
  assert.equal(noBackendRows[0].spread, null);
});

test("market overview schedules the earliest non-expired opportunity expiry", () => {
  const expiry = nextMarketOverviewExpiryMs(
    [
      opportunity({ valid_until_utc: "2026-09-09T02:59:59Z" }),
      opportunity({ opportunity_id: "later", valid_until_utc: "2026-09-09T03:02:00Z" }),
      opportunity({ opportunity_id: "earlier", valid_until_utc: "2026-09-09T03:01:00Z" }),
      opportunity({ opportunity_id: "status-expired", status: "expired", valid_until_utc: "2026-09-09T03:00:45Z" }),
    ],
    nowMs,
  );

  assert.equal(expiry, Date.parse("2026-09-09T03:01:00Z"));
});

test("market overview schedules no timeout when no eligible expiry remains", () => {
  assert.equal(
    nextMarketOverviewExpiryMs(
      [
        opportunity({ valid_until_utc: "2026-09-09T02:59:59Z" }),
        opportunity({ status: "expired", valid_until_utc: "2026-09-09T04:00:00Z" }),
      ],
      nowMs,
    ),
    null,
  );
});

test("market overview formats both quote sides with one shared unit", () => {
  assert.equal(formatQuoteBidAsk(31.11, 31.18, "EUR/MWh"), "31.11 / 31.18 EUR/MWh");
  assert.equal(formatQuoteBidAsk(null, 31.18, "EUR/MWh"), "n/a / 31.18 EUR/MWh");
  assert.equal(formatQuoteBidAsk(31.11, null, "EUR/MWh"), "31.11 / n/a EUR/MWh");
});
