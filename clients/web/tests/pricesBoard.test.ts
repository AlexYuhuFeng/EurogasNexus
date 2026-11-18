/**
 * Desk → Prices (CP-20): the board's hub set, the reporting-unit request and its answers, the
 * multi-hub term structure through the normalisation service, the link into Spreads, and the
 * palette selecting its last query when reopened (so a new conversion replaces it).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { NormaliseResponseDTO } from "../src/api/comparablePrices.ts";
import {
  BOARD_DEFAULT_HUBS,
  BOARD_HUBS_KEY,
  MAX_BOARD_HUBS,
  boardReportingRequest,
  readBoardHubs,
  reportingByHub,
  withHub,
  withoutHub,
  writeBoardHubs,
} from "../src/app/model/priceBoard.ts";
import { compareRequest, comparedCurves, monthCode, spreadsLink } from "../src/app/model/termStructureCompare.ts";

const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

test("board hubs: the six majors by default, kept per browser, never empty or over the cap", () => {
  const store = new Map<string, string>();
  const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
  assert.deepEqual(readBoardHubs(storage), [...BOARD_DEFAULT_HUBS]);
  writeBoardHubs(withHub(BOARD_DEFAULT_HUBS, "CEGH"), storage);
  assert.deepEqual(readBoardHubs(storage), [...BOARD_DEFAULT_HUBS, "CEGH"]);
  store.set(BOARD_HUBS_KEY, "not json");
  assert.deepEqual(readBoardHubs(storage), [...BOARD_DEFAULT_HUBS]);
  assert.deepEqual(withoutHub(["TTF"], "TTF"), ["TTF"]);
  const many = Array.from({ length: 20 }, (_, index) => `H${String.fromCharCode(65 + index)}X`);
  assert.equal(many.reduce((hubs, hub) => withHub(hubs, hub), [] as string[]).length, MAX_BOARD_HUBS);
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(readBoardHubs(broken), [...BOARD_DEFAULT_HUBS]);
  writeBoardHubs(["TTF"], broken);
});

test("reporting unit: only prices not already in EUR/MWh are sent, with the tenor's product", () => {
  const { body, hubs } = boardReportingRequest([
    { hub: "TTF", tenor: "month-ahead", value: 42.472, unit: "EUR/MWh" },
    { hub: "NBP", tenor: "month-ahead", value: 98.654, unit: "p/th" },
    { hub: "NBP", tenor: "day-ahead", value: null, unit: "p/th" },
  ]);
  assert.deepEqual(hubs, ["NBP"]);
  assert.deepEqual(body, { to_unit: "EUR/MWh", values: [{ value: 98.654, unit: "GBp/th", product: "M+1" }] });
  const response = {
    values: [{
      value: 39.408, unit: "EUR/MWh", native: { value: 98.654, unit: "p/th" }, simulated: true,
      normalisation: { fx: { method: "derived: covered interest parity", label: "derived (…)", desk_quote: { pair: "EUR/GBP", rate: 0.8542, spot_rate: 0.853 } } },
    }],
    series: null,
  } as unknown as NormaliseResponseDTO;
  const nbp = reportingByHub(hubs, response).get("NBP");
  assert.equal(nbp?.value, 39.408);
  assert.equal(nbp?.pair, "EUR/GBP");
  assert.equal(nbp?.simulated, true);
});

test("several hubs: each month goes to the server with its product; answers line up by month", () => {
  assert.equal(monthCode("2027-01"), "Jan-27");
  const curves = [
    { hub: "TTF", months: ["2027-01", "2027-02"], values: [30, 31], unit: "EUR/MWh" },
    { hub: "NBP", months: ["2027-01", "2029-01"], values: [78, 80], unit: "GBp/th" },
  ];
  const { body, keys } = compareRequest(curves);
  assert.equal(body.to_unit, "EUR/MWh");
  assert.deepEqual(body.values.map((item) => item.product), ["Jan-27", "Feb-27", "Jan-27", "Jan-29"]);
  const response = {
    values: [
      { value: 30, simulated: false, normalisation: { fx: null } },
      { value: 31, simulated: false, normalisation: { fx: null } },
      { value: 30.5, simulated: false, normalisation: { fx: { method: "derived: covered interest parity", label: "derived (interest parity from SONIA, €STR, flat rate)" } } },
      { value: null, simulated: false, refused: { code: "beyond_horizon", message: "not convertible: Jan-29 …" } },
    ],
    series: null,
  } as unknown as NormaliseResponseDTO;
  const compared = comparedCurves(curves, keys, response);
  assert.deepEqual(compared.months, ["2027-01", "2027-02", "2029-01"]);
  assert.deepEqual(compared.series.find((item) => item.hub === "NBP")?.values, [30.5, null, null]);
  assert.equal(compared.beyondHorizon, 1);
  assert.deepEqual(compared.fxLabels, ["derived (interest parity from SONIA, €STR, flat rate)"]);
});

test("the spread by delivery month is a link into Spreads with the pair described", () => {
  const href = spreadsLink("?workspace=market&task=curves", "NBP");
  const params = new URLSearchParams(href.slice(1));
  assert.equal(params.get("workspace"), "research");
  assert.equal(params.get("task"), "spreads");
  assert.equal(params.get("describe"), "forward spread net of transport tariff between TTF and NBP");
  assert.match(new URLSearchParams(spreadsLink("", "TTF").slice(1)).get("describe") ?? "", /TTF and NBP$/);
});

test("Prices: no bar spread, no standing converter panel; the board prints native units", () => {
  const charts = read("components/PriceCharts.tsx");
  assert.doesNotMatch(charts, /style: "bar"/);
  assert.match(charts, /data-spread-link/);
  const cockpit = read("components/MarketCockpit.tsx");
  assert.doesNotMatch(cockpit, /TraderDeskPanel/);
  const terminal = read("components/MarketTerminal.tsx");
  assert.match(terminal, /inNative\(/);
  assert.match(terminal, /data-reporting/);
});

test("the command palette selects its last query when reopened, so typing replaces it", () => {
  const palette = read("components/CommandPalette.tsx");
  assert.match(palette, /autoFocus[\s\S]{0,300}onFocus=\{\(event\) => event\.currentTarget\.select\(\)\}/);
});
