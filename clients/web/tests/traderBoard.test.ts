/**
 * Desk → Board (SMALL_DESK_PLAN step 4): the board's contracts and cells (native units, bid and
 * offer, stale, "no source"), the spreads (sign, unit, the transport rule both ways), the
 * position on the board's rows, the detail panel's series and its "no source" state, and the
 * selection wiring from a cell to the panel. Figures are illustrative, not market prices.
 */
import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { MarketObsDTO, MarketQuoteDTO, PositionLadderRowDTO } from "../src/api/client.ts";
import type { BoardTenorDTO, SpreadBoardDTO } from "../src/api/spreads.ts";
import {
  BOARD_HUBS,
  THERMS_PER_MWH,
  boardContracts,
  buildBoard,
  contractOfQuote,
  inHubUnit,
  pairsParam,
  positionOnBoard,
  spreadFigure,
  timeSpreads,
} from "../src/app/model/traderBoardModel.ts";
import {
  DEFAULT_SELECTION,
  curveShape,
  dailyCloses,
  forwardCurves,
  historyProduct,
  intradayPoints,
  intradaySummary,
  MIN_INTRADAY_POINTS,
  observationSeries,
  selectionKey,
  spreadHistory,
} from "../src/app/model/traderDetailModel.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const h = React.createElement;
const t = (key: string, options?: Record<string, unknown>) =>
  options && Object.keys(options).length ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${String(v)}`).join(",")})` : key;

const GAS_DAY = "2026-11-27";
const NOW = Date.parse("2026-11-27T10:00:00Z");

function quote(over: Partial<MarketQuoteDTO>): MarketQuoteDTO {
  return {
    quote_id: `q-${over.hub}-${over.product}-${over.source_system ?? "X"}`,
    source_system: "EEX",
    venue: "EEX",
    instrument_id: "i",
    hub: "TTF",
    product: "day-ahead",
    delivery_start_utc: "2026-11-28T05:00:00Z",
    delivery_end_utc: "2026-11-29T05:00:00Z",
    bid_price: 30,
    ask_price: 30.1,
    last_price: 30.05,
    currency: "EUR",
    unit: "MWh",
    observed_at_utc: "2026-11-27T09:59:30Z",
    received_at_utc: "2026-11-27T09:59:30Z",
    source_reference: "r",
    freshness: "live",
    quality_score: 1,
    simulated: false,
    stale_after_seconds: 60,
    ...over,
  };
}

/* ------------------------------------------------------------------ contracts */

test("the board's rows are the owner's twelve contracts, named as the execution screen names them", () => {
  const contracts = boardContracts(GAS_DAY);
  assert.deepEqual(
    contracts.map((item) => item.label),
    ["WD", "DA", "WE", "BOM", "Dec-26", "Jan-27", "Feb-27", "Q1-27", "Q2-27", "Sum-27", "Win-27", "Cal-27"],
  );
  // In summer the next season not started is the winter, then the summer after it.
  assert.deepEqual(boardContracts("2027-05-10").filter((item) => item.kind === "season").map((item) => item.label), ["Win-27", "Sum-28"]);
  // A quote finds its row by product word or by its delivery window.
  assert.equal(contractOfQuote({ product: "month-ahead", delivery_start_utc: "", delivery_end_utc: "" }, contracts)?.key, "M1");
  assert.equal(contractOfQuote({ product: "q1-27", delivery_start_utc: "2027-01-01T05:00:00Z", delivery_end_utc: "2027-04-01T04:00:00Z" }, contracts)?.label, "Q1-27");
  assert.equal(contractOfQuote({ product: "cal-28", delivery_start_utc: "2028-01-01T05:00:00Z", delivery_end_utc: "2029-01-01T05:00:00Z" }, contracts), null);
});

test("each hub in its own quotation: NBP's GBP/MWh is pence per therm, never through FX", () => {
  assert.equal(inHubUnit("TTF", 30, "EUR", "MWh"), 30);
  assert.ok(Math.abs((inHubUnit("NBP", 30, "GBP", "MWh") ?? 0) - (30 * 100) / THERMS_PER_MWH) < 1e-9);
  assert.equal(inHubUnit("NBP", 87.5, "GBp", "th"), 87.5);
  // An NBP quote stored in EUR would need an FX rate: not shown as a p/th figure.
  assert.equal(inHubUnit("NBP", 30, "EUR", "MWh"), null);
  assert.equal(inHubUnit("TTF", 30, "GBP", "MWh"), null);
});

test("a cell: bid and offer, last and the change on the day; stale and 'no source' are said", () => {
  const contracts = boardContracts(GAS_DAY);
  const quotes = [
    quote({ hub: "TTF", close_price: 29.5, close_kind: "close", close_day: "2026-11-26" }),
    quote({ hub: "NBP", currency: "GBP", unit: "MWh", bid_price: 30, ask_price: 30.2, last_price: 30.1 }),
    // An NBP quote in EUR from another feed does not take the cell from the GBP one.
    quote({ hub: "NBP", source_system: "OTHER", currency: "EUR", observed_at_utc: "2026-11-27T09:59:50Z" }),
    // Old beyond its source's 60-second cadence.
    quote({ hub: "THE", observed_at_utc: "2026-11-27T09:50:00Z" }),
    // A simulated quote never beats a real one for its cell.
    quote({ hub: "ZTP", source_system: "EEX_Sim", simulated: true, bid_price: 99, ask_price: 99.1, observed_at_utc: "2026-11-27T09:59:59Z" }),
    quote({ hub: "ZTP", bid_price: 31, ask_price: 31.1 }),
  ];
  const cells = buildBoard(quotes, contracts, BOARD_HUBS, NOW);
  const ttf = cells.DA!.TTF!;
  assert.equal(ttf.status, "priced");
  assert.equal(ttf.bid, 30);
  assert.equal(ttf.offer, 30.1);
  assert.equal(ttf.last, 30.05);
  assert.ok(Math.abs((ttf.change ?? 0) - 0.55) < 1e-9, "mid 30.05 against the close 29.5");
  assert.equal(ttf.unit, "EUR/MWh");
  const nbp = cells.DA!.NBP!;
  assert.equal(nbp.unit, "p/th");
  assert.equal(nbp.source, "EEX");
  assert.ok(Math.abs((nbp.bid ?? 0) - (30 * 100) / THERMS_PER_MWH) < 1e-9);
  assert.equal(cells.DA!.THE!.stale, true);
  assert.equal(ttf.stale, false);
  assert.equal(cells.DA!.ZTP!.bid, 31);
  assert.equal(cells.DA!.ZTP!.simulated, false);
  assert.equal(cells.DA!.PVB!.status, "no_source");
  assert.equal(cells.DA!.PVB!.bid, null, "no source is never a number");
  assert.equal(cells.CAL1!.TTF!.status, "no_source");
});

test("the price board renders native units, bid and offer, the stale mark and 'no source', and each cell selects its chart", async () => {
  const { load } = await loadApiStore();
  const { PriceBoard } = await load<typeof import("../src/components/TraderScreen.tsx")>("/src/components/TraderScreen.tsx");
  const contracts = boardContracts(GAS_DAY);
  const cells = buildBoard([quote({ hub: "TTF" }), quote({ hub: "THE", observed_at_utc: "2026-11-27T09:00:00Z" })], contracts, BOARD_HUBS, NOW);
  const html = renderToStaticMarkup(h(PriceBoard, { contracts, cells, t, onSelect: () => undefined, selected: "price:DA:TTF" }));
  for (const hub of BOARD_HUBS) assert.match(html, new RegExp(`${hub}<span class="ds-grid-unit">${hub === "NBP" ? "p/th" : "EUR/MWh"}`));
  assert.match(html, /board\.bid/);
  assert.match(html, /board\.offer/);
  assert.match(html, />30\.000</);
  assert.match(html, />30\.100</);
  assert.match(html, /data-no-source="PVB"[^>]*>board\.no_source</);
  assert.match(html, /data-cell="DA:THE"[^>]*data-stale="true"/);
  assert.match(html, /ds-stale-mark/);
  // Selection wiring: every cell names its selection; the chosen one is pressed.
  assert.match(html, /data-select="price:DA:TTF" aria-pressed="true"/);
  assert.match(html, /data-select="price:CAL1:NBP" aria-pressed="false"/);
  assert.match(html, /data-select="curve:TTF"/);
  assert.equal(selectionKey(DEFAULT_SELECTION), "price:M1:TTF", "the panel opens on TTF's front month");
});

/* ------------------------------------------------------------------ spreads */

function tenor(over: Partial<BoardTenorDTO>): BoardTenorDTO {
  return {
    tenor: "DA",
    available: true,
    gross: -1.0,
    cost: 0.4,
    direction: "TTF → NBP",
    close_day: "2026-11-26",
    legs: [
      { hub: "TTF", native_value: 30, native_unit: "EUR/MWh", value: 30 },
      { hub: "NBP", native_value: 75, native_unit: "GBp/th", value: 31 },
    ],
    route: {
      hubs: ["TTF", "NBP"],
      through: [],
      complete: true,
      missing: [],
      product: "DAILY",
      gas_years: [],
      issues: [],
      marginal: { product: "DAILY", capacity: 0.3, commodity: 0.05, fuel_pct: 0.1, fuel: 0.05, flow_not_held: [], total: 0.4, holder: 0.1, capacity_held: "none", sunk_capacity: null },
    },
    ...over,
  };
}

test("a spread keeps its sign; an NBP leg puts it in p/th at the close's own rate", () => {
  const figure = spreadFigure(tenor({}));
  const factor = 75 / 31;
  assert.equal(figure.unit, "p/th");
  assert.ok(Math.abs((figure.gross ?? 0) - -1.0 * factor) < 1e-9, "TTF − NBP stays negative");
  assert.ok(Math.abs((figure.gbpPerEur ?? 0) - (factor * THERMS_PER_MWH) / 100) < 1e-9);
  const eur = spreadFigure(tenor({ legs: [{ hub: "TTF", native_value: 30, native_unit: "EUR/MWh", value: 30 }, { hub: "THE", native_value: 30.5, native_unit: "EUR/MWh", value: 30.5 }], gross: 0.5 }));
  assert.equal(eur.unit, "EUR/MWh");
  assert.equal(eur.gross, 0.5);
  assert.equal(pairsParam(), "TTF-NBP,ZTP-NBP,TTF-ZTP,TTF-THE,PVB-TTF");
});

test("transport rule: short-term capacity plus flow by default; the flow charge alone where booked", () => {
  const eur = { legs: [{ hub: "TTF", native_value: 30, native_unit: "EUR/MWh", value: 30 }, { hub: "THE", native_value: 31, native_unit: "EUR/MWh", value: 31 }], gross: 1.0 };
  const free = spreadFigure(tenor(eur));
  assert.equal(free.basis, "default");
  assert.equal(free.transport, 0.4);
  assert.ok(Math.abs((free.net ?? 0) - 0.6) < 1e-9);
  const booked = tenor(eur);
  booked.route!.marginal!.capacity_held = "all";
  const held = spreadFigure(booked);
  assert.equal(held.basis, "held");
  assert.equal(held.transport, 0.1);
  assert.ok(Math.abs((held.net ?? 0) - 0.9) < 1e-9);
  const partly = tenor(eur);
  partly.route!.marginal!.capacity_held = "part";
  assert.equal(spreadFigure(partly).basis, "part");
  assert.equal(spreadFigure(partly).transport, 0.4, "part booked is still priced on the default");
  const unpriced = spreadFigure(tenor({ ...eur, cost: null, route: undefined }));
  assert.equal(unpriced.basis, "unpriced");
  assert.equal(unpriced.net, null, "no route cost, no net");
});

test("time spreads: DA − WD from the board's mids, the rest from the server in the hub's quotation", () => {
  const contracts = boardContracts(GAS_DAY);
  const cells = buildBoard([quote({ hub: "TTF" }), quote({ hub: "TTF", product: "within-day", bid_price: 29.8, ask_price: 29.9 })], contracts, BOARD_HUBS, NOW);
  const board = { time: [{ hub: "NBP", unit: "GBP/MWh", rows: [{ key: "da_ma", label: "DA − MA", available: true, value: -0.5, native_value: -1.47 }], simulated: false }] } as unknown as SpreadBoardDTO;
  const time = timeSpreads(board, cells, BOARD_HUBS);
  assert.ok(Math.abs((time.da_wd.TTF!.value ?? 0) - 0.2) < 1e-9);
  assert.equal(time.da_wd.NBP!.value, null);
  assert.equal(time.da_ma.NBP!.value, -1.47);
  assert.equal(time.da_ma.NBP!.unit, "p/th");
});

/* ------------------------------------------------------------------ position */

test("position on the board's rows: MW on the continent, th/d at NBP; no daily figure for the prompt days", () => {
  const contracts = boardContracts(GAS_DAY);
  const row = (hub: string, month: string, physical: number, financial: number): PositionLadderRowDTO =>
    ({ hub, month, physical_mwh: physical, financial_mwh: financial, net_mwh: physical + financial, hedge_ratio: null }) as PositionLadderRowDTO;
  const position = positionOnBoard([row("TTF", "2026-12", 744 * 10, 0), row("NBP", "2026-12", 31 * 1000, -31 * 500)], contracts, BOARD_HUBS);
  assert.equal(position.M1!.TTF!.net, 10, "7,440 MWh over 744 hours is 10 MW");
  assert.equal(position.M1!.TTF!.unit, "MW");
  assert.ok(Math.abs((position.M1!.NBP!.physical ?? 0) - 1000 * THERMS_PER_MWH) < 1e-6);
  assert.ok(Math.abs((position.M1!.NBP!.net ?? 0) - 500 * THERMS_PER_MWH) < 1e-6);
  assert.equal(position.M1!.NBP!.unit, "th/d");
  assert.equal(position.DA!.TTF!.prompt, true);
  assert.equal(position.DA!.TTF!.net, null);
});

/* ------------------------------------------------------------------ detail panel */

function obs(price: number, at: string, source = "EEX", hub = "TTF", tenor = "month-ahead"): MarketObsDTO & { hub: string; tenor: string } {
  return { observation_id: `${at}-${source}`, market_venue: "x", product: `${hub} ${tenor}`, price, unit: "MWh", currency: "EUR", period_start_utc: at, period_end_utc: at, observed_at_utc: at, source_system: source, hub, tenor };
}

test("the detail panel's price series: real history wins, one close a day, today's ticks end at the board's mid", () => {
  const contracts = boardContracts(GAS_DAY);
  assert.equal(historyProduct(contracts.find((item) => item.key === "M1")!, "TTF"), "TTF month-ahead");
  assert.equal(historyProduct(contracts.find((item) => item.key === "Q1")!, "NBP"), "NBP Q1-27");
  const rows = [obs(30, "2026-11-25T16:00:00Z"), obs(31, "2026-11-26T09:00:00Z"), obs(31.5, "2026-11-26T16:00:00Z"), obs(99, "2026-11-26T17:00:00Z", "EEX_Sim"), obs(32, "2026-11-27T08:00:00Z")];
  const series = observationSeries(rows, "TTF");
  assert.equal(series.simulated, false);
  assert.ok(!series.points.some((point) => point.value === 99), "a simulated row never joins a real line");
  assert.deepEqual(dailyCloses(series.points, "2026-11-01").map((point) => point.value), [30, 31.5, 32]);
  const today = intradayPoints(series.points, "2026-11-27T05:00:00.000Z", quote({ product: "month-ahead", observed_at_utc: "2026-11-27T09:59:30Z" }), "TTF");
  assert.deepEqual(today.map((point) => point.value), [32, 30.05]);
  // Only simulated rows: the series says so (drawn with the sim mark, never as a market line).
  assert.equal(observationSeries([obs(1, "2026-11-27T08:00:00Z", "EEX_Sim")], "TTF").simulated, true);
});

test("the intraday panel needs three prices today: fewer is a calm line, not a chart", () => {
  const start = "2026-11-27T05:00:00.000Z";
  const point = (value: number, at: string) => ({ at, value });
  const live = quote({ product: "month-ahead", close_price: 29.5, observed_at_utc: "2026-11-27T09:59:30Z" });
  // One stored tick plus the board's mid: two points is not a line.
  const two = intradaySummary([point(30, "2026-11-26T16:00:00Z"), point(31, "2026-11-27T08:00:00Z")], start, live, "TTF");
  assert.equal(MIN_INTRADAY_POINTS, 3);
  assert.equal(two.enough, false);
  assert.equal(two.points.length, 2);
  assert.equal(two.last?.value, 30.05, "the last point is the board's mid");
  assert.equal(two.priorClose, 29.5, "the prior close is the quote's own close");
  // Three today's prices is enough to draw.
  const three = intradaySummary([point(30, "2026-11-26T16:00:00Z"), point(31, "2026-11-27T07:00:00Z"), point(31.2, "2026-11-27T08:00:00Z"), point(31.5, "2026-11-27T09:00:00Z")], start, null, "TTF");
  assert.equal(three.enough, true);
  assert.equal(three.last?.value, 31.5);
  assert.equal(three.priorClose, 30, "without a quote close the last held close is stated");
});

test("the forward curve today against a day and a week ago, and its shape", () => {
  const rows = [
    obs(30, "2026-11-27T08:00:00Z", "EEX", "TTF", "2026-12"),
    obs(31, "2026-11-27T08:00:00Z", "EEX", "TTF", "2027-01"),
    obs(29, "2026-11-26T08:00:00Z", "EEX", "TTF", "2026-12"),
    obs(28, "2026-11-19T08:00:00Z", "EEX", "TTF", "2026-12"),
  ];
  const curve = forwardCurves(rows, "TTF");
  assert.deepEqual(curve.months, ["2026-12", "2027-01"]);
  assert.deepEqual(curve.today, [30, 31]);
  assert.deepEqual(curve.dayAgo, [29, null]);
  assert.deepEqual(curve.weekAgo, [28, null]);
  assert.equal(curveShape(curve.today), "contango");
  assert.equal(curveShape([31, 30]), "backwardation");
  assert.equal(curveShape([30]), null);
});

test("a spread's history in the board's unit; nothing held is 'no source', never a line", async () => {
  const history = spreadHistory(tenor({ spark: { days: ["2026-11-25", "2026-11-26"], values: [-1, -0.8] }, range: { low: -2, high: 1, days: 250 } }), 2, 0.8);
  assert.deepEqual(history?.values, [-2, -1.6]);
  assert.equal(history?.low, -4);
  assert.equal(history?.transport, 0.8);
  assert.equal(spreadHistory(tenor({ available: false }), null, null), null);
  const { load } = await loadApiStore();
  const { TraderDetail } = await load<typeof import("../src/components/TraderDetail.tsx")>("/src/components/TraderDetail.tsx");
  const html = renderToStaticMarkup(
    h(TraderDetail, {
      selection: { kind: "spread", pair: "PVB–TTF", tenor: "DA" },
      contracts: boardContracts(GAS_DAY),
      quotes: [],
      markets: [],
      spreads: null,
      flows: null,
      lng: null,
      points: null,
      gasDay: GAS_DAY,
      nowMs: NOW,
      t,
      height: 200,
      patterns: {},
    }),
  );
  assert.match(html, /data-detail="spread"/);
  assert.match(html, /data-detail-state="no-source"/);
  assert.match(html, /board\.no_source/);
  assert.match(html, /board\.detail\.spread_no_source/);
  assert.doesNotMatch(html, /<canvas/);
  // A flow line with nothing held says so too.
  const flow = renderToStaticMarkup(
    h(TraderDetail, {
      selection: { kind: "flow", key: "iuk" },
      contracts: boardContracts(GAS_DAY),
      quotes: [],
      markets: [],
      spreads: null,
      flows: null,
      lng: null,
      points: [],
      gasDay: GAS_DAY,
      nowMs: NOW,
      t,
      height: 200,
      patterns: { iuk: /iuk/i },
    }),
  );
  assert.match(flow, /data-detail-state="no-source"/);
});

/* ------------------------------------------------------------------ what just happened */

import type { NewsItemDTO, NewsSourceDTO, OutageEventDTO } from "../src/api/client.ts";
import { boardEvents, hubsFor, isAlertEvent, licensedSlot } from "../src/app/model/traderEventsModel.ts";

function outage(over: Partial<OutageEventDTO>): OutageEventDTO {
  return {
    event_id: "e1", version: 1, facility_id: "f", facility_name: "Field A", asset_type: "production", event_type: "unplanned",
    status: "active", start_utc: "2026-11-27T08:00:00Z", end_utc: "2026-11-28T14:00:00Z", published_at_utc: "2026-11-27T09:30:00Z",
    balancing_zone: "NBP", unit: "mcm/d", unavailable_capacity: 12, capacity_impact_mcm_d: 12, description: "", market_participant: "x",
    unavailable_gwh_d: 132, source_system: "GIE_IIP", ...over,
  };
}

function newsItem(over: Partial<NewsItemDTO>): NewsItemDTO {
  return {
    item_id: "n1", source_id: "govuk-desnz", source_title: "", publisher: "GOV.UK", url: null, title: "Storage levels statement", summary: "",
    language: "en", published_at_utc: "2026-11-27T09:45:00Z", retrieved_at_utc: null, licence_note: "", event_types: [], entities: [],
    hubs: [], countries: ["GB"], capacity_change: false, linked_event_key: null, revision: 1, first_seen_at_utc: null,
    relevance: { score: 0, matches: 0, roles: [], reasons: [] }, book_hidden: false, ...over,
  };
}

test("events: newest first, mapped to the desk's hubs, the book marked, a repeated REMIT event once", () => {
  assert.deepEqual(hubsFor(["GB"]), ["NBP"]);
  assert.deepEqual(hubsFor(["NO"]), ["NBP", "TTF", "ZTP", "THE"]);
  assert.deepEqual(hubsFor(["ES", "DE"]), ["THE", "PVB"]);
  assert.deepEqual(hubsFor(["PEG"]), [], "a hub outside the desk's five bears on none of them");
  const events = boardEvents(
    [
      outage({}),
      outage({ event_id: "e2", event_type: "planned", balancing_zone: "TTF", published_at_utc: "2026-11-26T10:00:00Z", capacity_impact_mcm_d: null, unavailable_gwh_d: 97.5 }),
      outage({ event_id: "e3", status: "ended", published_at_utc: "2026-11-27T09:59:00Z" }),
    ],
    [newsItem({}), newsItem({ item_id: "n2", linked_event_key: "e1", published_at_utc: "2026-11-27T09:50:00Z" })],
    new Set(["TTF"]),
  );
  assert.deepEqual(events.map((event) => event.key), ["news:n1", "outage:e1", "outage:e2"]);
  const nbp = events[1]!;
  assert.equal(nbp.kind, "unplanned");
  assert.deepEqual(nbp.hubs, ["NBP"]);
  assert.deepEqual(nbp.size, { value: -12, unit: "mcm/d" }, "GB in mcm/d");
  assert.equal(nbp.touchesBook, false);
  assert.deepEqual(nbp.select, { kind: "price", contract: "DA", hub: "NBP" });
  const ttf = events[2]!;
  assert.equal(ttf.kind, "planned");
  assert.deepEqual(ttf.size, { value: -97.5, unit: "GWh/d" }, "the continent in GWh/d");
  assert.equal(ttf.touchesBook, true, "the desk holds a position at TTF");
});

test("the alert rule: a new unplanned event at one of the five hubs; planned work and news never alarm", () => {
  const now = Date.parse("2026-11-27T10:00:00Z");
  const list = boardEvents(
    [outage({}), outage({ event_id: "e2", event_type: "planned", published_at_utc: "2026-11-27T09:40:00Z" })],
    [newsItem({ published_at_utc: "2026-11-27T09:59:00Z" })],
    new Set(),
  );
  const [news, planned, unplanned] = list;
  assert.equal(unplanned!.kind, "unplanned");
  assert.equal(isAlertEvent(unplanned!, now), true);
  assert.equal(isAlertEvent(planned!, now), false);
  assert.equal(isAlertEvent(news!, now), false);
  assert.equal(isAlertEvent(unplanned!, now + 2 * 3_600_000), false, "after an hour it is standing, not new");
  const [elsewhere] = boardEvents([outage({ balancing_zone: "PEG" })], [], new Set());
  assert.equal(isAlertEvent(elsewhere!, now), false, "not at the desk's hubs");
});

test("licensed headline feeds are an empty slot to connect, never read or simulated", async () => {
  const sources = [
    { source_id: "remit-umm", publisher: "REMIT", reuse: "permitted" },
    { source_id: "wire", publisher: "Reuters, Argus", reuse: "licensed" },
  ] as unknown as NewsSourceDTO[];
  assert.deepEqual(licensedSlot(sources), { publishers: "Reuters, Argus" });
  assert.equal(licensedSlot([]), null);
  const { load } = await loadApiStore();
  const { Events } = await load<typeof import("../src/components/TraderScreen.tsx")>("/src/components/TraderScreen.tsx");
  const html = renderToStaticMarkup(h(Events, { events: boardEvents([outage({})], [], new Set()), nowMs: Date.parse("2026-11-27T10:00:00Z"), t, licensed: licensedSlot(sources) }));
  assert.match(html, /data-licensed-slot="empty"/);
  assert.match(html, /board\.events\.licensed_slot\(publishers=Reuters, Argus\)/);
  assert.match(html, /data-alert="true"/);
  assert.match(html, /board\.events\.kind\.unplanned/);
});
