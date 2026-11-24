/**
 * QA-T-01, T-03, T-04 on the hub board: the mid is (bid + ask) / 2 or nothing (never the last
 * trade, which has its own column), a one-sided quote is marked as such, the change vs the
 * previous close is signed in absolute and percent with the close's day on hover, and a stale
 * row says "stale" with its age rather than relying on colour.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { MarketQuoteDTO } from "../src/api/client.ts";
import {
  changeVsClose,
  formatChangeVsClose,
  isQuoteStale,
  latestUpdateStamp,
  quoteClose,
  quoteMid,
  quoteOneSided,
  quoteStaleAfterSeconds,
} from "../src/app/model/boardQuote.ts";

const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

function quote(overrides: Partial<MarketQuoteDTO>): MarketQuoteDTO {
  return {
    quote_id: "q",
    source_system: "EEX_Sim",
    venue: "EEX (simulated)",
    instrument_id: "EEX-TTF-DA",
    hub: "TTF",
    product: "day-ahead",
    delivery_start_utc: "2026-11-25T05:00:00Z",
    delivery_end_utc: "2026-11-26T05:00:00Z",
    bid_price: 41.405,
    ask_price: 41.47,
    last_price: 41.475,
    currency: "EUR",
    unit: "MWh",
    observed_at_utc: "2026-11-24T13:50:00Z",
    received_at_utc: "2026-11-24T13:50:00Z",
    source_reference: "feed:simulated-exchange",
    freshness: "simulated",
    quality_score: 0,
    simulated: true,
    ...overrides,
  };
}

test("mid is (bid + ask) / 2, never the last trade (QA-T-01: TTF 41.405/41.470 last 41.475)", () => {
  assert.equal(quoteMid(quote({})), (41.405 + 41.47) / 2);
  // NBP from the QA run: 103.780 / 104.030 with last 104.010; the true mid is 103.905.
  assert.equal(quoteMid(quote({ bid_price: 103.78, ask_price: 104.03, last_price: 104.01 })), 103.905);
  assert.equal(quoteMid(quote({ bid_price: null, last_price: 41.5 })), null);
  assert.equal(quoteMid(null), null);
});

test("a one-sided quote shows its side, never the last as a mid", () => {
  assert.deepEqual(quoteOneSided(quote({ ask_price: null })), { side: "bid", value: 41.405 });
  assert.deepEqual(quoteOneSided(quote({ bid_price: null })), { side: "ask", value: 41.47 });
  assert.equal(quoteOneSided(quote({})), null);
  assert.equal(quoteOneSided(quote({ bid_price: null, ask_price: null })), null);
});

test("change vs close: signed absolute and percent, from the newest quote carrying a close", () => {
  const history = [
    quote({ quote_id: "streamed" }), // a streamed quote arrives without the close
    quote({ quote_id: "read", close_price: 41.2, close_day: "2026-11-23", close_kind: "settlement", close_source_system: "DEMO_Sim", close_simulated: true }),
  ];
  const close = quoteClose(history);
  assert.deepEqual(close, { price: 41.2, day: "2026-11-23", kind: "settlement", sourceSystem: "DEMO_Sim", simulated: true });
  const up = changeVsClose(41.45, 41.2);
  assert.ok(up);
  assert.equal(formatChangeVsClose(up), "+0.250 (+0.61 %)");
  const down = changeVsClose(41.0, 41.2);
  assert.ok(down);
  assert.equal(formatChangeVsClose(down), "−0.200 (−0.49 %)");
  assert.equal(changeVsClose(null, 41.2), null);
  assert.equal(changeVsClose(41.0, null), null);
  assert.equal(changeVsClose(1, 0)?.percent, null);
  assert.equal(quoteClose([quote({})]), null);
  // A feed's prior settlement states no day.
  assert.equal(quoteClose([quote({ close_price: 41.47, close_day: null, close_kind: "prior_settlement" })])?.day, null);
});

test("stale: older than the source's cadence on the browser clock, else as the server judged", () => {
  const history = [quote({}), quote({ stale_after_seconds: 60 })];
  assert.equal(quoteStaleAfterSeconds(history), 60);
  assert.equal(isQuoteStale(quote({}), 2 * 86_400, 60), true);
  assert.equal(isQuoteStale(quote({}), 30, 60), false);
  assert.equal(isQuoteStale(quote({ freshness_state: "STALE" }), null, null), true);
  assert.equal(isQuoteStale(quote({ freshness_state: "FRESH" }), 120, null), false);
  assert.equal(isQuoteStale(null, 999, 60), false);
});

test("the board takes the mid from the model, shows Last and change vs close, and marks stale rows in words", () => {
  const terminal = read("components/MarketTerminal.tsx");
  assert.doesNotMatch(terminal, /last_price\)\) return quote\.last_price/);
  assert.match(terminal, /from "@\/app\/model\/boardQuote"/);
  assert.match(terminal, /id: "last"/);
  assert.match(terminal, /id: "change-vs-close"/);
  assert.match(terminal, /market\.stale_label/);
  assert.match(terminal, /"is-live is-stale"/);
  assert.match(terminal, /market\.as_of_title/);
  assert.match(read("styles/prices.css"), /tr\.is-stale/);
});

test("every new board string is in English and Chinese", () => {
  const en = JSON.parse(read("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(read("i18n/zh.json")) as Record<string, string>;
  for (const key of [
    "market.last", "market.last_title", "market.chg_vs_close", "market.chg_vs_close_title",
    "market.close_basis", "market.close_kind.close", "market.close_kind.settlement",
    "market.close_kind.prior_settlement", "market.close_day_unstated", "market.one_sided.bid",
    "market.one_sided.ask", "market.one_sided_title", "market.stale_label", "market.stale_description",
    "market.as_of_title", "prices.board.spread_stale_label", "prices.board.spread_stale",
  ]) {
    assert.ok(en[key], `en ${key}`);
    assert.ok(zh[key], `zh ${key}`);
  }
});

test("QA-R-05: the Updated stamp is never later than the server received or read the data", () => {
  // A tick stamped two days ahead shows the time it was received, not the future.
  assert.equal(
    latestUpdateStamp([
      { observed_at_utc: "2026-11-26T14:07:00Z", received_at_utc: "2026-11-24T14:07:00Z" },
      { observed_at_utc: "2026-11-24T13:00:00Z", received_at_utc: "2026-11-24T13:00:01Z" },
    ]),
    "2026-11-24T14:07:00.000Z",
  );
  // Rows without a receive time (observations) are capped at the server's read instant.
  assert.equal(
    latestUpdateStamp([{ observed_at_utc: "2026-11-26T14:07:00Z" }], "2026-11-24T14:10:00Z"),
    "2026-11-24T14:10:00.000Z",
  );
  // An ordinary row is shown as observed.
  assert.equal(
    latestUpdateStamp([{ observed_at_utc: "2026-11-24T14:00:00Z", received_at_utc: "2026-11-24T14:00:02Z" }], "2026-11-24T14:10:00Z"),
    "2026-11-24T14:00:00.000Z",
  );
  assert.equal(latestUpdateStamp([], "2026-11-24T14:10:00Z"), null);
  assert.match(read("stores/api.ts"), /latestUpdateStamp\(/);
});
