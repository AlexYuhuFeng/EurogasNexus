/**
 * A glossary entry for a trader: concepts are definitions, entities carry their figures with
 * source and time, the gas day reads one CAM day, a hub shows the map card's prices, and links
 * (`term=`, `place=`) resolve any case or alias.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { GlossaryContextDTO, NodeDTO, NormalizedMarketObsDTO } from "../src/api/client.ts";
import {
  contextAnswers,
  entryCapacity,
  entryLinks,
  entryPrices,
  gasDayReadWindow,
  glossaryHubCode,
  glossaryMapPlace,
  glossaryTermSearch,
  isEntityTerm,
  mapPlaceFromSearch,
  mapPlaceSearch,
  resolveGlossaryTerm,
  uniqueSources,
} from "../src/app/model/glossaryEntry.ts";

const terms = [
  { term_id: "hub-nbp", term: "NBP", category: "hub", aliases: ["National Balancing Point"] },
  { term_id: "hub-etf", term: "ETF", category: "hub", aliases: ["Exchange Transfer Facility"] },
  { term_id: "price-bid", term: "Bid", category: "price", aliases: [] },
  { term_id: "venue-ice-ocm", term: "ICE OCM", category: "venue", aliases: ["OCM"] },
  { term_id: "price-icis-heren", term: "ICIS Heren", category: "price", aliases: [] },
  { term_id: "ip-zee", term: "Zeebrugge Entry Point", category: "interconnection", aliases: [] },
];

const node = (id: string, name: string, node_type: string): NodeDTO =>
  ({ id, name, node_type, country: "GB", lat: 53, lon: -1, capacity_boe_d: null });
const nodes = [node("hub-nbp", "NBP", "hub"), node("easington", "Easington", "entry_point")];

function context(partial: Partial<GlossaryContextDTO>): GlossaryContextDTO {
  return {
    term: "NBP",
    context_type: "hub",
    description: "",
    matched_entities: [],
    capacity: null,
    capacity_usage: null,
    metrics: [],
    related_prices: [],
    related_routes: [],
    related_contracts: [],
    live_market_marks: [],
    context_sections: [],
    related_sources: [],
    data_quality: {},
    warnings: [],
    research_only: true,
    human_review_required: true,
    ...partial,
  };
}

test("a link or a search resolves the entry by term, alias or id in any case", () => {
  assert.equal(resolveGlossaryTerm("nbp", terms)?.term_id, "hub-nbp");
  assert.equal(resolveGlossaryTerm("National balancing point", terms)?.term_id, "hub-nbp");
  assert.equal(resolveGlossaryTerm("HUB-NBP", terms)?.term_id, "hub-nbp");
  assert.equal(resolveGlossaryTerm("ocm", terms)?.term_id, "venue-ice-ocm");
  assert.equal(resolveGlossaryTerm("nothing", terms), null);
  assert.equal(resolveGlossaryTerm(null, terms), null);
});

test("concepts are definitions; hubs, venues, assessments and points are entities", () => {
  const nbp = terms[0];
  assert.equal(isEntityTerm(nbp, glossaryMapPlace(nbp, nodes)), true);
  assert.equal(isEntityTerm(terms[2], null), false, "a bid is a concept: no figures, no date");
  assert.equal(isEntityTerm(terms[3], null), true);
  assert.equal(isEntityTerm(terms[4], null), true);
  assert.equal(isEntityTerm(terms[5], null), true);
  // A term the platform resolves to an entry point is an entity even from a generic category.
  assert.equal(isEntityTerm({ term: "Bacton", category: "contract" }, null, { context_type: "entry_point" }), true);
  assert.equal(isEntityTerm({ term: "Entry Capacity", category: "capacity" }, null, { context_type: "capacity" }), false);
});

test("an entity the map draws links to its network node, and the link round-trips", () => {
  assert.equal(glossaryMapPlace(terms[0], nodes), "hub-nbp");
  assert.equal(glossaryMapPlace(terms[1], nodes), null, "ETF is not on the map");
  assert.equal(glossaryMapPlace({ term: "Easington", category: "point" }, nodes), "easington");
  assert.equal(glossaryHubCode(terms[0], nodes), "NBP");
  assert.equal(glossaryHubCode(terms[0], []), "NBP", "a zone hub reads the board before the geometry loads");
  assert.equal(glossaryHubCode(terms[3], nodes), null, "a venue is not a hub");
  const map = mapPlaceSearch("?workspace=glossary&term=NBP", "hub-nbp");
  assert.equal(mapPlaceFromSearch(map), "hub-nbp");
  assert.equal(new URLSearchParams(map).get("task"), "network");
  assert.equal(new URLSearchParams(map).get("term"), null, "the entry's term stays on the glossary");
  const search = new URLSearchParams(glossaryTermSearch(map, "NBP"));
  assert.equal(search.get("workspace"), "glossary");
  assert.equal(search.get("term"), "NBP");
  assert.equal(search.get("place"), null, "the map's place stays on the map's page");
});

test("a gas day reads one CAM day, a second inside each end; none reads the latest", () => {
  assert.deepEqual(gasDayReadWindow(""), {});
  // Winter: 05:00 UTC to 05:00 UTC.
  assert.deepEqual(gasDayReadWindow("2026-11-26"), {
    duration_start_utc: "2026-11-26T05:00:01.000Z",
    duration_end_utc: "2026-11-27T04:59:59.000Z",
  });
  // Summer: 04:00 UTC.
  assert.equal(gasDayReadWindow("2026-06-01").duration_start_utc, "2026-06-01T04:00:01.000Z");
  // The October change: the day starts at 04:00 and ends at 05:00 UTC.
  assert.equal(gasDayReadWindow("2026-10-24").duration_end_utc, "2026-10-25T04:59:59.000Z");
});

test("the context answers only the term and the gas day it was read for", () => {
  const nbp = terms[0];
  assert.equal(contextAnswers(context({ requested_duration: null }), nbp, ""), true);
  assert.equal(contextAnswers(context({ term: "TTF" }), nbp, ""), false);
  const day = context({ requested_duration: { duration_start_utc: "2026-11-26T05:00:01+00:00" } });
  assert.equal(contextAnswers(day, nbp, "2026-11-26"), true);
  assert.equal(contextAnswers(day, nbp, "2026-11-25"), false);
  assert.equal(contextAnswers(day, nbp, ""), false, "a dated read does not stand for the latest");
});

test("a map hub with no gas day shows the board's prices, as the map card does", () => {
  const board = [
    { hub: "NBP", tenor: "day-ahead", is_gas_price: true, price: 80.5, unit: "GBp/th", observed_at_utc: "2026-11-26T09:00:00Z", source_system: "ICE" },
    { hub: "NBP", tenor: "day-ahead", is_gas_price: true, price: 80.0, unit: "GBp/th", observed_at_utc: "2026-11-25T09:00:00Z", source_system: "ICE" },
  ] as unknown as NormalizedMarketObsDTO[];
  const figures = entryPrices(null, { hub: "NBP", gasDay: "", boardRows: board });
  assert.equal(figures.length, 1);
  assert.equal(figures[0].tenor, "day-ahead");
  assert.equal(figures[0].value, 80.5);
  assert.equal(figures[0].change, 0.5);
  assert.equal(figures[0].source, "ICE");
  assert.equal(figures[0].asOf, "2026-11-26T09:00:00Z");
  // A chosen gas day reads the platform's rows for that day instead.
  assert.deepEqual(entryPrices(context({}), { hub: "NBP", gasDay: "2026-11-20", boardRows: board }), []);
});

test("each venue and product shows its latest reading once, with source and time", () => {
  const figures = entryPrices(
    context({
      related_prices: [
        { market_venue: "ICIS Heren", product: "NBP DA", price: 29.0, unit: "GBP/MWh", observed_at_utc: "2026-06-01T10:00:00Z", source_reference: "licensed:a" },
        { market_venue: "ICIS Heren", product: "NBP DA", price: 29.15, unit: "GBP/MWh", observed_at_utc: "2026-06-01T12:00:00Z", source_reference: "licensed:b" },
        { market_venue: "ICIS Heren", product: "NBP DA", price: "n/a", unit: "GBP/MWh" },
      ],
      live_market_marks: [
        { venue: "ICE OCM", hub: "NBP", product: "within-day", bid_gbp_mwh: 29.4, ask_gbp_mwh: 29.6, last_gbp_mwh: null, mark_time_utc: "2026-06-01T12:30:00Z", source_reference: "screen:x" },
      ],
    }),
    { hub: null, gasDay: "2026-06-01", boardRows: [] },
  );
  assert.equal(figures.length, 2);
  assert.equal(figures[0].label, "ICE OCM · NBP within-day");
  assert.equal(figures[0].value, 29.5, "no last: the mid of bid and ask");
  assert.equal(figures[0].detail, "29.4 / 29.6");
  assert.equal(figures[1].value, 29.15);
  assert.equal(figures[1].source, "licensed:b");
});

test("capacity, its use, routes and contracts are named figures, not raw records", () => {
  const read = context({
    capacity: { point_name: "TTF", direction: "exit", firmness: "firm", capacity_mwh_per_day: 100000, valid_from_utc: "2026-06-01T06:00:00Z", source_reference: "customer-capacity-profile" },
    capacity_usage: { used: 63300, unit: "MWh/d", usage_pct: 63.3, period_end_utc: "2026-06-02T06:00:00Z", source_reference: "entsog:ttf:bbl" },
    related_routes: [{ route_id: "r1", route_name: "TTF -> BBL -> NBP virtual sale" }, { route_id: "r1", route_name: "TTF -> BBL -> NBP virtual sale" }],
    related_contracts: [{ contract_id: "c1", contract_name: "TTF BBL portfolio" }],
  });
  const capacity = entryCapacity(read);
  assert.deepEqual(capacity.map((figure) => [figure.id, figure.value, figure.unit]), [["capacity", 100000, "MWh/d"], ["capacity_used", 63300, "MWh/d"]]);
  assert.equal(capacity[0].label, "TTF · exit · firm");
  assert.equal(capacity[1].detail, "63.3 %");
  assert.deepEqual(entryLinks(read), { routes: ["TTF -> BBL -> NBP virtual sale"], contracts: ["TTF BBL portfolio"] });
  assert.deepEqual(entryCapacity(null), []);
});

test("a term's sources are listed once", () => {
  assert.deepEqual(uniqueSources(["ICE", "EEX", "ice", " "], ["EEX", "ECB"]), ["ICE", "EEX", "ECB"]);
});
