/**
 * The regas auction desk on screen (Desk → Cargoes → Regas auctions): the states' words and
 * tones, the countdowns, the auction window's time zone, the request bodies, and the live
 * wiring (the answer re-reads on price, FX, mark and limit notices through the session's one
 * live stream). Nothing here bids or orders.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import type { RegasCaseInputsDTO } from "../src/api/regasAuction.ts";
import {
  REGAS_LIVE_MS,
  REGAS_LIVE_TOPICS,
  bodyFromInputs,
  countdownText,
  deadlineTone,
  draftGaps,
  draftToBody,
  emptyDraft,
  isBidLevel,
  missingSummary,
  quotedUnit,
  secondsUntil,
  stateTone,
  utcToZoned,
  withCost,
  withHandPrice,
  withLevel,
  zonedToUtc,
} from "../src/app/model/regasAuctionModel.ts";
import { MARKET_TASKS } from "../src/app/model/marketCockpitModel.ts";
import { PRODUCT_MODES, modeLocationFor } from "../src/app/navigation/modeNavigation.ts";

import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

// The live hook imports through the app's aliases: the harness's Vite server resolves them.
after(closeApiStoreHarness);
type UseLiveModule = typeof import("../src/app/hooks/useLive.ts");

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the three headroom states read room, at the limit and stop in green, amber and red", () => {
  assert.equal(stateTone("room"), "ok");
  assert.equal(stateTone("at_limit"), "watch");
  assert.equal(stateTone("stop"), "breach");
  assert.equal(stateTone("illustration"), "simulated");
  assert.equal(stateTone("missing_inputs"), "watch");
  assert.equal(stateTone("no_level"), "neutral");
  assert.equal(isBidLevel({ computed: true, simulated: false }), true);
  assert.equal(isBidLevel({ computed: true, simulated: true }), false, "a simulated answer is never a bid level");
  assert.equal(isBidLevel({ computed: false, simulated: false }), false);
});

test("countdowns and their urgency follow the alert lead times", () => {
  assert.equal(countdownText(2 * 86_400 + 4 * 3_600 + 5 * 60), "2d 04:05");
  assert.equal(countdownText(3_725), "01:02:05");
  assert.equal(countdownText(0, "closed"), "closed");
  assert.equal(countdownText(null), "–");
  const now = Date.parse("2026-12-02T15:00:00Z");
  assert.equal(secondsUntil("2026-12-02T16:00:00Z", now), 3_600);
  assert.equal(deadlineTone(3 * 3_600), "neutral");
  assert.equal(deadlineTone(90 * 60), "watch");
  assert.equal(deadlineTone(20 * 60), "breach");
  assert.equal(deadlineTone(-1), "stale");
});

test("the auction window is entered in the operator's time zone and sent in UTC", () => {
  assert.equal(zonedToUtc("2026-12-02T17:00", "Europe/Amsterdam"), "2026-12-02T16:00:00Z");
  assert.equal(zonedToUtc("2027-07-01T09:30", "Europe/Amsterdam"), "2027-07-01T07:30:00Z");
  assert.equal(zonedToUtc("2026-12-02T17:00", "Europe/London"), "2026-12-02T17:00:00Z");
  assert.equal(utcToZoned("2026-12-02T16:00:00Z", "Europe/Amsterdam"), "2026-12-02T17:00");
  assert.equal(zonedToUtc("not a time", "Europe/Amsterdam"), null);
});

test("a new case body carries only what the trader entered, and says what is still needed", () => {
  const draft = emptyDraft(undefined);
  assert.deepEqual(draftGaps(draft), ["book", "terminal", "slot_days", "quantity", "closes", "owner", "price"]);
  const filled = {
    ...draft,
    book_id: "desk-a",
    terminal_id: "gate-terminal",
    terminal_name: "Gate (Rotterdam)",
    hub: "TTF",
    first_day: "2027-01-10",
    last_day: "2027-01-13",
    quantity: "1000",
    closes_local: "2026-12-02T17:00",
    owner_id: "owner-1",
    owner_name: "Cargo Owner One",
    price: "28.00",
    costs: { berthing: { value: "120000", link: "https://example.org/t" }, storage: { value: "", link: "" } },
  };
  assert.deepEqual(draftGaps(filled), []);
  const body = draftToBody(filled);
  assert.equal(body.auction.closes_at, "2026-12-02T16:00:00Z");
  assert.deepEqual(body.costs, { berthing: { value: "120000", link: "https://example.org/t" } });
  assert.equal(body.prices, undefined, "no hand price unless one is typed");
  assert.equal(body.terminal.terminal_id, "gate-terminal");
});

test("changing a stored case keeps its version and every hand entry", () => {
  const inputs: RegasCaseInputsDTO = {
    schema: 1,
    title: "Gate slot",
    terminal: { terminal_id: "gate-terminal", name: "Gate", hub: "TTF", by_hand: false },
    slot: { first_day: "2027-01-10", last_day: "2027-01-13", quantity: "1000", unit: "GWh", factor: null, factor_source: null },
    auction: { format: "rising_rounds", opens_at: null, closes_at: "2026-12-02T16:00:00Z", time_zone: "Europe/Amsterdam", quotation: "per_mwh", level: { value: "0.40", by: "a", at: "x" }, level_history: [], notice_key: null, link: null },
    owner: { counterparty_id: "owner-1", name: "Owner", by_hand: false },
    offer: { kind: "fixed", price: "28.00", price_unit: "EUR/MWh", tolerance_pct: "5", expires_at: null },
    profile: { weights: null },
    delay_days: 0,
    costs: { berthing: { value: "120000", by: "a", at: "x", link: "https://example.org/t" } },
    prices: { TTF: { all: { value: "30.60", by: "a", at: "x" } } },
    fx: null,
    rate_pct: { value: "2.5", by: "a", at: "x" },
  };
  const body = bodyFromInputs(inputs, 3);
  assert.equal(body.version, 3);
  assert.deepEqual(body.costs, { berthing: { value: "120000", link: "https://example.org/t" } });
  assert.deepEqual(body.prices, { TTF: { all: "30.60" } });
  assert.equal(body.rate_pct, "2.5");
  assert.equal(withLevel(body, "0.55").auction.level, "0.55");
  assert.equal(withLevel(body, " ").auction.level, null);
  assert.deepEqual(withCost(body, "storage", "5000").costs?.storage, { value: "5000" });
  assert.equal(withCost(body, "berthing", "").costs?.berthing, undefined);
  assert.deepEqual(withHandPrice(body, "TTF", "").prices?.TTF, {});
});

test("missing inputs are grouped: one line per hub's prices", () => {
  assert.deepEqual(missingSummary(["price:TTF:2027-01-10", "price:TTF:2027-01-11", "cost:berthing", "financing_rate"]), [
    { kind: "price", what: "TTF", count: 2 },
    { kind: "cost", what: "berthing", count: 1 },
    { kind: "financing_rate", what: "financing_rate", count: 1 },
  ]);
  assert.equal(quotedUnit({ currency: "EUR", quotation: "per_mwh" }), "EUR/MWh");
  assert.equal(quotedUnit({ currency: "GBP", quotation: "per_slot" }), "GBP");
});

test("the answer re-reads on price, FX, mark and limit notices, a burst once", async () => {
  const { createLiveRereader } = await (await loadApiStore()).load<UseLiveModule>("/src/app/hooks/useLive.ts");
  assert.deepEqual([...REGAS_LIVE_TOPICS], ["prices", "book"]);
  let now = 0;
  const pending: Array<{ fn: () => void; at: number }> = [];
  let fired = 0;
  const rereader = createLiveRereader(() => (fired += 1), REGAS_LIVE_MS, [], 250, () => now, {
    set: (fn, ms) => { const entry = { fn, at: now + ms }; pending.push(entry); return entry; },
    clear: (handle) => { const index = pending.indexOf(handle as (typeof pending)[number]); if (index >= 0) pending.splice(index, 1); },
  });
  rereader.notice("prices");
  rereader.notice("prices");
  rereader.notice("book");
  assert.equal(fired, 1, "the first notice re-reads at once");
  now = REGAS_LIVE_MS;
  pending.splice(0).forEach((entry) => entry.fn());
  assert.equal(fired, 2, "the rest of the burst re-reads once at the end of the interval");
  const panel = read("../src/components/RegasAuctionPanel.tsx");
  assert.match(panel, /useLiveTopics\(REGAS_LIVE_TOPICS, read\.refresh, \{ minIntervalMs: REGAS_LIVE_MS \}\)/);
  assert.match(panel, /useNow\(1_000\)/, "the countdowns tick every second");
});

test("the tool is a view of the one LNG workspace, not a page, and never orders", () => {
  assert.ok(MARKET_TASKS.includes("auctions"));
  const desk = PRODUCT_MODES.find((mode) => mode.id === "desk")!;
  const cargoes = desk.tasks.find((task) => task.id === "cargoes")!;
  assert.deepEqual(cargoes.alsoPageTasks, ["auctions"]);
  assert.equal(desk.tasks.some((task) => task.pageTask === "auctions"), false, "no third LNG task");
  assert.equal(modeLocationFor("market", "auctions")?.task.id, "cargoes");
  const panel = read("../src/components/RegasAuctionPanel.tsx");
  assert.match(panel, /<Button size="sm" disabled title=\{answer\.prepare_hedge_orders\.note\} data-regas-prepare-orders="">/);
  assert.doesNotMatch(panel, /submit(Bid|Order)|placeOrder|sendOrder/);
  const css = read("../src/components/regas-auction.css");
  // Colours, sizes and spacing are tokens (npm run lint:css checks the file); only breakpoints and
  // the hairline border are raw.
  const body = css.replace(/\/\*[\s\S]*?\*\//g, "").replace(/@media[^{]*\{/g, "");
  assert.doesNotMatch(body, /#[0-9a-f]{3,6}\b|\b(?!1px)\d+px/i, "tokens only");
});

test("every regas string has English and Chinese", () => {
  const en = JSON.parse(read("../src/i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;
  const keys = Object.keys(en).filter((key) => key.startsWith("regas.") || key.startsWith("lng.view."));
  assert.ok(keys.length > 150);
  for (const key of keys) {
    assert.ok(zh[key], `zh ${key}`);
  }
  for (const state of ["room", "at_limit", "stop", "no_level", "illustration", "missing_inputs"]) {
    assert.ok(en[`regas.state.${state}`] && zh[`regas.state.${state}`], state);
  }
});
