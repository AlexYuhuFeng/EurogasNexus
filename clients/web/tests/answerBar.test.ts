/**
 * The answer bar: routing over recorded queries (the routing eval), the tier 2 look-ups shaped
 * from stubbed reads, and the rows rendered as the palette renders them.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { AskAnswerDTO, DeskTodayDTO, UnitsReferenceDTO } from "../src/api/client.ts";
import type { AnswerView } from "../src/app/answer/answerModel.ts";
import { lookupIntent } from "../src/app/answer/intent.ts";
import { lookup, type AnswerReads } from "../src/app/answer/lookups.ts";
import { routeQuery } from "../src/app/answer/route.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const UNITS = JSON.parse(readFileSync(new URL("./fixtures/unitsReference.json", import.meta.url), "utf8")) as UnitsReferenceDTO;
const CASES = JSON.parse(readFileSync(new URL("./fixtures/answerRoutingCases.json", import.meta.url), "utf8")).cases as Array<{
  query: string; kind: string; intent?: string; book?: boolean;
}>;
const GLOSSARY = [
  { term: "TTF", aliases: ["Title Transfer Facility"], definition_en: "Title Transfer Facility, the Dutch hub.", definition_zh_cn: "荷兰产权转让设施。" },
  { term: "Hedge ratio", aliases: ["对冲比率"], definition_en: "Share of exposure hedged." },
  { term: "UMM", aliases: ["Urgent Market Message"], definition_en: "A REMIT outage disclosure." },
];
const NOW = new Date("2026-11-16T12:00:00Z");

test("routing eval: every recorded query reaches its tier", () => {
  const wrong: string[] = [];
  for (const item of CASES) {
    const route = routeQuery(item.query, {
      units: UNITS, fx: null, glossary: GLOSSARY, bookAllowed: item.book ?? true, zh: false, now: NOW,
    });
    const intent = route.kind === "lookup" ? route.intent.kind : undefined;
    if (route.kind !== item.kind || (item.intent && intent !== item.intent)) {
      wrong.push(`${item.query}: ${route.kind}${intent ? `/${intent}` : ""}, wanted ${item.kind}${item.intent ? `/${item.intent}` : ""}`);
    }
  }
  assert.deepEqual(wrong, []);
});

test("tier 1 is synchronous and fast: a thousand routed queries well under 5 ms each", () => {
  const queries = CASES.map((item) => item.query);
  const started = performance.now();
  for (let round = 0; round < 25; round += 1) {
    for (const query of queries) routeQuery(query, { units: UNITS, fx: null, glossary: GLOSSARY, bookAllowed: true, zh: false, now: NOW });
  }
  const perQuery = (performance.now() - started) / (25 * queries.length);
  assert.ok(perQuery < 5, `${perQuery.toFixed(3)} ms per query`);
});

function today(): DeskTodayDTO {
  return {
    as_of: "2026-11-16T12:00:00Z", gas_day: "2026-11-16", front_month: "Dec-26", simulated: true, simulated_notice: null,
    stale_figures: [], warnings: [],
    rows: [
      {
        key: "key_figures", title: "", populated: true, prices_empty: null, position_empty: null, limit_empty: null, tightest_limit: null,
        prices: [{ key: "price.TTF", label: "TTF Dec-26", value: 42.472, unit: "EUR/MWh", as_of: "2026-11-15T12:00:00Z", state: "current",
          simulated: true, source: "Demo price", hub: "TTF", product: "Dec-26", tenor: "month-ahead", close_day: "2026-11-15",
          day_change: -0.166, day_change_vs: "2026-11-14" }],
        position: {
          today: { key: "p", label: "Net position today", value: 46000, unit: "MWh/d", as_of: "2026-11-16", state: "current", simulated: false, source: null },
          front_month: { key: "f", label: "Net position Dec-26", value: 28516.1, unit: "MWh/d", as_of: "2026-11-16", state: "current", simulated: false, source: null },
        },
      },
      { key: "changes", title: "", populated: true, empty: null, alerts: { counts: { open: 0, critical: 0, warning: 0 }, items: [], more: 0, listed_elsewhere: 0 },
        outages: { counts: { active: 0, scheduled: 0, total: 0 }, horizon_days: 14, as_of: null, state: "current", items: [], more: 0 } },
      { key: "book", title: "", populated: true, empty: null, hubs: [] },
      { key: "fundamentals", title: "", populated: true, empty: null,
        storage: { latest: { key: "s", label: "NW Europe storage fill", value: 72.62, unit: "%", as_of: "2026-11-15", state: "current", simulated: true, source: "Demo" },
          inventory_twh: 385.47, unit: "%", series: [{ day: "2026-11-15", inventory_twh: 385.47, fill_pct: 72.62 }] },
        balance: { latest: { key: "b", label: "call", value: 9273.8, unit: "GWh/d", as_of: "2026-11-15", state: "current", simulated: true, source: "Demo" }, unit: "GWh/d",
          series: Array.from({ length: 8 }, (_, i) => ({ day: `2026-11-${String(8 + i).padStart(2, "0")}`, call_gwh: 9000, norway_gwh: 4418 - (i === 7 ? 30 : 0), lng_gwh: 2800, storage_net_withdrawal_gwh: 1500 })) },
      },
    ],
  } as unknown as DeskTodayDTO;
}

function reads(overrides: Partial<AnswerReads> = {}): AnswerReads {
  return {
    deskToday: async () => today(),
    normalizedPrices: async () => ({
      limit: 2000,
      rows: [{ hub: "NBP", tenor: "2027-01", price: 35.4, unit: "GBP/MWh", currency: "GBP", observed_at_utc: "2026-11-16T11:54:00Z",
        source_system: "DEMO_Sim", metadata_json: { simulated: true }, is_gas_price: true }] as never,
    }),
    quotes: async () => [],
    storage: async () => null,
    lng: async () => [],
    outages: async () => [
      { event_id: "1", facility_name: "Haldor field", facility_id: "H", balancing_zone: "NBP", status: "active", unavailable_gwh_d: 563.2,
        unavailable_capacity: 52, unit: "mcm/d", end_utc: "2026-11-19T09:00:00Z", published_at_utc: "2026-11-16T09:00:00Z", source_reference: "demo:umm" },
      { event_id: "2", facility_name: "Kestrel line", facility_id: "K", balancing_zone: "TTF", status: "active", unavailable_gwh_d: 97.5,
        unavailable_capacity: 9, unit: "mcm/d", end_utc: null, published_at_utc: "2026-11-15T06:00:00Z", source_reference: "demo:umm" },
    ] as never,
    ladder: async () => ({ rows: [{ hub: "NBP", month: "2026-12", net_mwh: 574000, physical_mwh: 1054000, financial_mwh: -480000 }], horizon: { start: "2026-11-16" } }) as never,
    credit: async () => ({ as_of: "2026-11-16", rows: [{ counterparty_id: "RHM", counterparty: "Rhinmark Handel GmbH", currency: "EUR", headroom: -491592,
      net_exposure: 4491592, limit: 4000000, utilisation_pct: 112.3, status: "breach" }] as never }),
    contracts: async () => [],
    normalise: async () => ({ values: [], series: null }),
    units: () => UNITS,
    ...overrides,
  };
}

async function answerFor(query: string, overrides: Partial<AnswerReads> = {}): Promise<AnswerView> {
  const intent = lookupIntent(query, { bookAllowed: true, now: NOW });
  assert.ok(intent, query);
  return lookup(intent, reads(overrides), new AbortController().signal);
}

test("a front-month price comes from the Today read, simulated and with its change", async () => {
  const answer = await answerFor("TTF");
  assert.equal(answer.label, "TTF Dec-26");
  assert.equal(answer.value, "42.472");
  assert.equal(answer.unit, "EUR/MWh");
  assert.equal(answer.simulated, true);
  assert.equal(answer.delta?.text, "−0.166");
  assert.deepEqual(answer.target, { kind: "task", mode: "desk", task: "prices" });
});

test("a curve month for NBP is shown in pence per therm, converted with the authority's factor", async () => {
  const answer = await answerFor("NBP Jan-27");
  assert.equal(answer.unit, "p/th");
  assert.equal(answer.value, (35.4 * 100 * UNITS.energy_in_mwh.th).toFixed(3));
  assert.equal(answer.simulated, true);
});

test("no sourced price says so as the board does, and a capped read says it was capped", async () => {
  const prompt = await answerFor("NBP DA");
  assert.equal(prompt.value, null);
  assert.deepEqual(prompt.sentence, { key: "answer.price.none" });
  assert.deepEqual(prompt.lines, [{ key: "market.awaiting_feed" }]);
  const capped = await answerFor("PEG Mar-27", { normalizedPrices: async () => ({ rows: new Array(2000).fill({ hub: "TTF", tenor: "2027-03" }) as never, limit: 2000 }) });
  assert.deepEqual(capped.lines, [{ key: "answer.price.capped" }]);
});

test("outages: active count, offline GWh/d over the sized ones, the largest first", async () => {
  const all = await answerFor("outages");
  assert.equal(all.value, "2");
  assert.equal(all.simulated, true);
  assert.equal(all.lines[0].key, "answer.outages.offline");
  assert.equal(all.lines[0].values?.gwh, "661");
  assert.match(String(all.lines[1].values?.items), /^Haldor field \(NBP\) 563 GWh\/d/);
  const nbp = await answerFor("UK outages");
  assert.equal(nbp.value, "1");
});

test("Norway and storage come from the Today read with their as-of and the week-earlier day", async () => {
  const norway = await answerFor("Norway");
  assert.equal(norway.value, "4,388");
  assert.equal(norway.delta?.text, "−30");
  // The day travels as an ISO date; answerText writes it in the reader's language.
  assert.deepEqual(norway.lines[0], { key: "answer.vs_day", values: { day: "2026-11-08" } });
  const harness = await loadApiStore();
  const { answerText } = await harness.load<typeof import("../src/components/AnswerBar.tsx")>("/src/components/AnswerBar.tsx");
  assert.equal(answerText(norway.lines[0], (key, values) => `${key}:${values?.day}`), "answer.vs_day:8 Nov");
  const storage = await answerFor("storage");
  assert.equal(storage.value, "72.6");
  const none = await answerFor("storage DE");
  assert.deepEqual(none.sentence, { key: "answer.storage.none_country", values: { country: "DE" } });
});

test("book look-ups: a month's position per day, credit headroom of a named counterparty", async () => {
  const position = await answerFor("position NBP Dec-26");
  assert.equal(position.value, "+18,516");
  assert.equal(position.unit, "MWh/d");
  const credit = await answerFor("credit rhinmark");
  assert.equal(credit.value, "−€491,592");
  assert.equal(credit.lines[0].key, "answer.credit.status.breach");
  assert.equal(lookupIntent("credit rhinmark", { bookAllowed: false }), null);
});

test("the answer row: an option with the value in tabular figures and the simulated mark beside it", async () => {
  const harness = await loadApiStore();
  const { AnswerRow, AskRow, AskPanel } = await harness.load<typeof import("../src/components/AnswerBar.tsx")>("/src/components/AnswerBar.tsx");
  const answer = await answerFor("TTF");
  const row = renderToStaticMarkup(React.createElement("ul", { role: "listbox" },
    React.createElement(AnswerRow, { answer, active: true, onHover: () => {}, onChoose: () => {} })));
  assert.match(row, /id="palette-answer" role="option" aria-selected="true"/);
  assert.match(row, /<span data-answer-value="true">42.472<\/span>/);
  assert.match(row, /class="ds-cell-mark" data-state="simulated"/);
  const ask = renderToStaticMarkup(React.createElement("ul", { role: "listbox" },
    React.createElement(AskRow, { question: "why did storage jump", aiAllowed: false, active: false, onHover: () => {}, onChoose: () => {} })));
  assert.match(ask, /id="palette-ask" role="option"/);
  assert.match(ask, /answer\.ask\.offer_off/);

  const result: AskAnswerDTO = {
    question: "q", topics: ["supply"], answer: null, basis: "facts", ai: "off", simulated: true, as_of: "2026-11-16T12:00:00Z",
    sources: ["balance:norway_gwh"], warnings: [],
    lines: [{ topic: "supply", text: "Norwegian supply 4,388 GWh/d on 15 Nov.", source: "balance:norway_gwh", as_of: "2026-11-15", simulated: true }],
  };
  const panel = renderToStaticMarkup(React.createElement(AskPanel, {
    state: { status: "done", question: "q", result }, onCancel: () => {}, onRetry: () => {}, onOpen: () => {}, onOpenReport: () => {},
  }));
  assert.match(panel, /answer\.ask\.facts_only/);
  assert.match(panel, /answer\.ask\.ai_off/);
  assert.match(panel, /Norwegian supply 4,388 GWh\/d on 15 Nov\./);
  assert.match(panel, /answer\.ask\.open\.supply/);
  assert.match(panel, /answer\.ask\.open_report/);
  const model = renderToStaticMarkup(React.createElement(AskPanel, {
    state: { status: "done", question: "q", result: { ...result, answer: "Norway was 4,388 GWh/d.", basis: "model", ai: "used" } },
    onCancel: () => {}, onRetry: () => {}, onOpen: () => {}, onOpenReport: () => {},
  }));
  assert.match(model, /answer\.ask\.ai_summary · why\.basis_model/);
  const running = renderToStaticMarkup(React.createElement(AskPanel, {
    state: { status: "running", question: "q", stage: "reading" }, onCancel: () => {}, onRetry: () => {}, onOpen: () => {}, onOpenReport: () => {},
  }));
  assert.match(running, /aria-busy="true"/);
  assert.match(running, /role="status"/);
});

test("the answer bar evaluates nothing: no eval, no Function, and Ask never runs per keystroke", () => {
  for (const file of ["expression.ts", "units.ts", "route.ts", "intent.ts", "lookups.ts", "gasDay.ts", "glossary.ts", "numbers.ts", "instant.ts"]) {
    const source = readFileSync(new URL(`../src/app/answer/${file}`, import.meta.url), "utf8");
    assert.doesNotMatch(source, /\beval\s*\(|new\s+Function\s*\(|\bFunction\s*\(/, file);
  }
  const hook = readFileSync(new URL("../src/app/hooks/useAnswerBar.ts", import.meta.url), "utf8");
  assert.match(hook, /LOOKUP_DEBOUNCE_MS = 250/);
  assert.match(hook, /controller\.abort\(\)/);
  // The model is reached only through runAsk, which only Enter or the Ask row calls.
  assert.equal(hook.match(/api\s*\.ask\(/g)?.length, 1);
  assert.match(hook.slice(hook.indexOf("const runAsk")), /api\s*\.ask\(/);
});
