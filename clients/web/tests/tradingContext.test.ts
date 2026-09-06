import assert from "node:assert/strict";
import test from "node:test";
import {
  euDstActiveOnUtc,
  gasDayLabelForUtc,
  gasDayStartUtc,
  marketMatchesTradingContext,
} from "../src/app/tradingContext.ts";

test("corrected EU-CAM gas day uses 05:00 UTC winter and 04:00 UTC summer", () => {
  assert.equal(gasDayStartUtc("2025-01-15"), Date.UTC(2025, 0, 15, 5));
  assert.equal(gasDayStartUtc("2025-07-15"), Date.UTC(2025, 6, 15, 4));
});

test("legacy wrong client anchors are absent from corrected implementation", () => {
  assert.notEqual(gasDayStartUtc("2025-01-15"), Date.UTC(2025, 0, 15, 4));
  assert.notEqual(gasDayStartUtc("2025-07-15"), Date.UTC(2025, 6, 15, 3));
});

test("gas day label rolls back before the boundary", () => {
  assert.equal(gasDayLabelForUtc(new Date("2025-01-15T04:59:00Z")), "2025-01-14");
  assert.equal(gasDayLabelForUtc(new Date("2025-01-15T05:00:00Z")), "2025-01-15");
  assert.equal(gasDayLabelForUtc(new Date("2025-07-15T03:59:00Z")), "2025-07-14");
  assert.equal(gasDayLabelForUtc(new Date("2025-07-15T04:00:00Z")), "2025-07-15");
});

test("DST transition days use exact next-boundary interval, not +24h", () => {
  const springPrevious = gasDayStartUtc("2025-03-29");
  const spring = gasDayStartUtc("2025-03-30");
  assert.equal(spring - springPrevious, 23 * 60 * 60 * 1000);
  const fallPrevious = gasDayStartUtc("2025-10-25");
  const fall = gasDayStartUtc("2025-10-26");
  assert.equal(fall - fallPrevious, 25 * 60 * 60 * 1000);
});

test("market trading-context matching honors the corrected half-open interval", () => {
  const base = {
    product: "TTF day-ahead",
    period_start_utc: "2025-07-15T04:00:00Z",
    period_end_utc: "2025-07-16T04:00:00Z",
  };
  assert.equal(marketMatchesTradingContext(base, "2025-07-15", "day-ahead"), true);
  assert.equal(
    marketMatchesTradingContext(
      { ...base, period_start_utc: "2025-07-14T04:00:00Z", period_end_utc: "2025-07-15T04:00:00Z" },
      "2025-07-15",
      "day-ahead",
    ),
    false,
  );
});

test("EU DST detection follows the last Sunday rule used by the corrected boundary", () => {
  assert.equal(euDstActiveOnUtc(2025, 0, 15), false);
  assert.equal(euDstActiveOnUtc(2025, 6, 15), true);
  assert.equal(euDstActiveOnUtc(2025, 2, 30), true);
  assert.equal(euDstActiveOnUtc(2025, 9, 26), false);
});
