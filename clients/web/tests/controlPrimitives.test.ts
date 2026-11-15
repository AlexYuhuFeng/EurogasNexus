/**
 * UX-02 second part, UX-03 and UX-05: Field, Select, Tabs, Segmented, Toolbar, Popover, Dialog,
 * Sheet, the DataGrid and the Today screen. The pure parts (keyboard movement, popover collision,
 * sorting, spans, figure wording) are tested directly; the components are rendered through the
 * project's Vite pipeline and checked for their semantics. The browser keyboard paths are driven
 * by `scripts/uat/keyboard_paths.mjs`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { DeskTodayDTO, RiskMethodNoteDTO } from "../src/api/client.ts";
import { gridRowIndex, rovingIndex } from "../src/components/ui/keyboard.ts";
import { placePopover } from "../src/components/ui/popoverPosition.ts";
import { nextSort, sortRows, spanRuns } from "../src/components/ui/dataGridModel.ts";
import { decimalsFor, formatChange, formatValue, stateWords } from "../src/app/model/todayModel.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

type Ui = typeof import("../src/components/ui/index.ts");
const h = React.createElement;
const render = (element: React.ReactElement) => renderToStaticMarkup(element);
const t = (key: string, options?: Record<string, unknown>) =>
  options && Object.keys(options).length ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${String(v)}`).join(",")})` : key;

async function ui(): Promise<Ui> {
  const { load } = await loadApiStore();
  return load<Ui>("/src/components/ui/index.ts");
}

/* ----------------------------------------------------------------- pure parts */

test("roving focus: wraps for tabs and segments, holds the ends for grid rows", () => {
  assert.equal(rovingIndex(0, 4, "ArrowRight"), 1);
  assert.equal(rovingIndex(3, 4, "ArrowRight"), 0);
  assert.equal(rovingIndex(0, 4, "ArrowLeft"), 3);
  assert.equal(rovingIndex(2, 4, "Home"), 0);
  assert.equal(rovingIndex(2, 4, "End"), 3);
  assert.equal(rovingIndex(2, 4, "ArrowDown"), null, "a horizontal list ignores Up/Down");
  assert.equal(rovingIndex(1, 4, "ArrowDown", { orientation: "vertical" }), 2);
  assert.equal(rovingIndex(3, 4, "ArrowRight", { wrap: false }), 3);
  assert.equal(gridRowIndex(0, 500, "ArrowUp"), 0);
  assert.equal(gridRowIndex(499, 500, "ArrowDown"), 499);
  assert.equal(gridRowIndex(3, 500, "PageDown"), 13);
  assert.equal(gridRowIndex(3, 500, "PageUp"), 0);
  assert.equal(gridRowIndex(3, 500, "End"), 499);
  assert.equal(gridRowIndex(3, 500, "Enter"), null);
});

test("popover placement: below, flipped above at the bottom, clamped at the edges, scrolls when tall", () => {
  const viewport = { width: 1366, height: 768 };
  const below = placePopover({ top: 100, left: 200, width: 40, height: 28 }, { width: 360, height: 200 }, viewport);
  assert.deepEqual(below, { top: 132, left: 200, maxHeight: 628, side: "bottom" });
  const flipped = placePopover({ top: 700, left: 200, width: 40, height: 28 }, { width: 360, height: 200 }, viewport);
  assert.equal(flipped.side, "top");
  assert.equal(flipped.top, 700 - 4 - 200);
  const right = placePopover({ top: 100, left: 1340, width: 20, height: 28 }, { width: 360, height: 100 }, viewport, "bottom-start");
  assert.equal(right.left, 1366 - 360 - 8, "kept inside the right edge");
  const end = placePopover({ top: 100, left: 300, width: 40, height: 28 }, { width: 360, height: 100 }, viewport, "bottom-end");
  assert.equal(end.left, 8, "end-aligned, clamped at the left gutter");
  const tall = placePopover({ top: 300, left: 10, width: 40, height: 28 }, { width: 360, height: 2000 }, viewport);
  assert.equal(tall.side, "bottom");
  assert.equal(tall.maxHeight, 768 - 328 - 4 - 8);
  const phone = placePopover({ top: 100, left: 10, width: 40, height: 28 }, { width: 360, height: 100 }, { width: 320, height: 640 });
  assert.equal(phone.left, 8);
});

test("sorting: stable, numeric, missing values last in both directions; headers alternate", () => {
  const rows = [
    { id: "a", v: 3 },
    { id: "b", v: null },
    { id: "c", v: -1 },
    { id: "d", v: 3 },
    { id: "e", v: Number.NaN },
  ];
  const asc = sortRows(rows, (row) => row.v, "ascending").map((row) => row.id);
  const desc = sortRows(rows, (row) => row.v, "descending").map((row) => row.id);
  assert.deepEqual(asc, ["c", "a", "d", "b", "e"]);
  assert.deepEqual(desc, ["a", "d", "c", "b", "e"]);
  assert.deepEqual(
    sortRows([{ p: "Q10-27" }, { p: "Q2-27" }, { p: "q1-27" }], (row) => row.p, "ascending").map((row) => row.p),
    ["q1-27", "Q2-27", "Q10-27"],
  );
  assert.deepEqual(nextSort(null, "net", "descending"), { columnId: "net", direction: "descending" });
  assert.deepEqual(nextSort({ columnId: "net", direction: "descending" }, "net"), { columnId: "net", direction: "ascending" });
  assert.deepEqual(nextSort({ columnId: "net", direction: "descending" }, "hub"), { columnId: "hub", direction: "ascending" });
  assert.deepEqual(spanRuns(["2026-12", "2026-12", "2027-01", "2027-02", "2027-02", "2027-02"]), [2, 0, 1, 3, 0, 0]);
  assert.deepEqual(spanRuns([]), []);
});

test("figures: decimals by unit, a signed change, the state in words only when not current", () => {
  assert.equal(decimalsFor("EUR/MWh"), 3);
  assert.equal(decimalsFor("MWh/d"), 0);
  assert.equal(decimalsFor("%"), 1);
  assert.equal(formatValue(46000, "MWh/d"), "46,000");
  assert.equal(formatValue(-534792, "EUR"), "−534,792");
  assert.equal(formatValue(33.662, "GBP/MWh"), "33.662");
  assert.equal(formatValue(null, "EUR"), "–", "a missing value is a dash, never zero");
  assert.equal(formatChange(-0.082, "GBP/MWh"), "−0.082");
  assert.equal(formatChange(0.1, "EUR/MWh"), "+0.100");
  assert.equal(formatChange(0, "EUR/MWh"), "0.000");
  const now = Date.parse("2026-11-15T12:00:00Z");
  assert.equal(stateWords({ state: "current", as_of: "2026-11-15T11:00:00Z" }, now, t), null);
  assert.equal(stateWords({ state: "late", as_of: "2026-11-15T09:00:00Z" }, now, t), "today.state.late(age=today.age.hours(count=3))");
  assert.equal(stateWords({ state: "stale", as_of: "2026-11-13" }, now, t), "today.state.stale(age=today.age.days(count=3))");
  assert.equal(stateWords({ state: "manual", as_of: null }, now, t), "today.state.manual");
});

/* ----------------------------------------------------------------- components */

test("Field wires label, hint and error to the control; Select is the native list", async () => {
  const { Field, Select } = await ui();
  const html = render(
    h(Field, { label: "Summary", hint: "One line", error: "Too short", children: h("input", { id: "summary", defaultValue: "" }) }),
  );
  assert.match(html, /<label class="ds-field-label" for="summary">Summary<\/label>/);
  assert.match(html, /<input id="summary" aria-describedby="summary-hint summary-error" aria-invalid="true"/);
  assert.match(html, /<small id="summary-error" class="ds-field-error" role="alert">Too short<\/small>/);
  const select = render(
    h(Select, { value: "6", onChange: () => undefined, "aria-label": "Horizon", options: [{ value: "3", label: "3 months" }, { value: "6", label: "6 months" }] }),
  );
  assert.match(select, /^<select aria-label="Horizon" class="ds-select ds-size-sm">/);
  assert.match(select, /<option value="6" selected="">6 months<\/option>/);
});

test("Tabs: one tablist, the active tab is selected and the only Tab stop", async () => {
  const { Tabs, WorkspaceTabs } = await ui();
  const html = render(
    h(Tabs, {
      idPrefix: "t",
      label: "Tasks",
      tabs: [{ id: "a", label: "Alpha" }, { id: "b", label: "Beta" }, { id: "c", label: "Gamma" }],
      activeId: "b",
      panelId: "panel",
      onChange: () => undefined,
    }),
  );
  assert.match(html, /role="tablist" aria-label="Tasks"/);
  assert.equal((html.match(/role="tab"/g) ?? []).length, 3);
  assert.match(html, /id="t-b" type="button" role="tab" aria-selected="true" aria-controls="panel" tabindex="0"/);
  assert.equal((html.match(/tabindex="0"/g) ?? []).length, 1);
  const nav = render(
    h(WorkspaceTabs, { idPrefix: "p", label: "Primary", tabs: [{ id: "x", label: "X" }], activeId: "x", panelId: "q", shellRegion: "navigation", onActivate: () => undefined }),
  );
  assert.match(nav, /^<nav class="ds-tabs ds-tabs-nav" role="tablist" aria-label="Primary" data-shell-region="navigation">/);
});

test("Segmented: a labelled group of pressed toggles with one Tab stop", async () => {
  const { Segmented } = await ui();
  const html = render(
    h(Segmented, {
      label: "Tenor",
      value: "DA",
      onChange: () => undefined,
      options: [
        { value: "WD", label: "WD", title: "Within-day" },
        { value: "DA", label: "DA", className: "market-tenor-tab", dataAttributes: { "data-tenor": "day-ahead" } },
      ],
    }),
  );
  assert.match(html, /<div class="ds-segmented ds-size-sm" role="group" aria-label="Tenor">/);
  assert.match(html, /aria-pressed="false" tabindex="-1" title="Within-day"/);
  assert.match(html, /aria-pressed="true" class="market-tenor-tab active" tabindex="0" data-tenor="day-ahead"/);
});

test("Toolbar: a labelled toolbar with a start and an end group", async () => {
  const { Toolbar } = await ui();
  const html = render(h(Toolbar, { label: "Board", end: h("span", null, "Updated") }, h("button", { type: "button" }, "Ladder")));
  assert.match(html, /^<div class="ds-toolbar" role="toolbar" aria-label="Board"><div class="ds-toolbar-start"><button type="button">Ladder<\/button><\/div><div class="ds-toolbar-end"><span>Updated<\/span><\/div><\/div>$/);
});

test("Popover: the trigger says it opens a dialog and is collapsed until pressed", async () => {
  const { Popover } = await ui();
  const html = render(
    h(Popover, {
      label: "Why: Rhinmark",
      trigger: (props: Record<string, unknown>) => {
        const { ref: _ref, ...rest } = props;
        return h("button", { ...rest, type: "button" }, "Why");
      },
      children: h("p", null, "Because"),
    }),
  );
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.doesNotMatch(html, /Because/, "the panel is not in the page while closed");
  const source = readFileSync(new URL("../src/components/ui/Popover.tsx", import.meta.url), "utf8");
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /triggerRef\.current\?\.focus\(/, "Escape returns focus to the trigger");
  assert.match(source, /popover: "manual"/, "drawn in the top layer");
});

test("Dialog and Sheet: one native dialog, labelled by its title, with a labelled close", async () => {
  const { Dialog, Sheet } = await ui();
  const closed = render(h(Dialog, { open: false, onClose: () => undefined, title: "Desk brief", closeLabel: "Close", children: "body" }));
  assert.match(closed, /^<dialog class="ds-dialog ds-dialog-md" aria-labelledby="[^"]+"><\/dialog>$/);
  const open = render(h(Dialog, { open: true, onClose: () => undefined, title: "Desk brief", closeLabel: "Close", footer: "f", children: "body" }));
  const id = /aria-labelledby="([^"]+)"/.exec(open)?.[1];
  assert.ok(id);
  assert.match(open, new RegExp(`<h2 id="${id}">Desk brief</h2>`));
  assert.match(open, /aria-label="Close" title="Close"/);
  assert.match(open, /<footer class="ds-dialog-foot">f<\/footer>/);
  const sheet = render(h(Sheet, { open: true, side: "full", onClose: () => undefined, title: "Rhinmark", label: "Inspector", closeLabel: "Close", hideClose: true, children: "x" }));
  assert.match(sheet, /^<dialog class="ds-sheet ds-sheet-full" aria-label="Inspector">/);
  assert.doesNotMatch(sheet, /aria-label="Close"/);
  const source = readFileSync(new URL("../src/components/ui/Dialog.tsx", import.meta.url), "utf8");
  assert.match(source, /showModal\(\)/, "modal: the page behind is inert");
  assert.match(source, /onCancel=\{\(event\) => \{\s*event\.preventDefault\(\);\s*onCloseRef\.current\(\);/, "Escape asks the owner to close");
  assert.match(source, /previous\.focus\(/, "focus returns to the opener");
});

/* ----------------------------------------------------------------- DataGrid */

interface Row {
  hub: string;
  month: string;
  net: number | null;
  simulated?: boolean;
}

function gridColumns(Ui: Ui) {
  void Ui;
  return [
    { id: "month", header: "Month", rowHeader: true, span: true, sortable: true, value: (row: Row) => row.month },
    { id: "hub", header: "Hub", sortable: true, value: (row: Row) => row.hub },
    {
      id: "net",
      header: "Net",
      unit: "MWh",
      type: "number" as const,
      sortable: true,
      value: (row: Row) => row.net,
      state: (row: Row) => (row.simulated ? { kind: "simulated" as const, label: "sim", description: "Simulated: not a market price" } : null),
    },
  ];
}

const ROWS: Row[] = [
  { hub: "NBP", month: "2026-12", net: 120 },
  { hub: "TTF", month: "2026-12", net: -40, simulated: true },
  { hub: "NBP", month: "2027-01", net: null },
];

test("DataGrid: a semantic table, figures right with the unit in the header, sortable headers", async () => {
  const Ui = await ui();
  const html = render(h(Ui.DataGrid<Row>, { label: "Position", columns: gridColumns(Ui), rows: ROWS, rowKey: (row: Row) => `${row.month}-${row.hub}` }));
  assert.match(html, /<table class="ds-grid ds-grid-regular" aria-label="Position">/);
  assert.equal((html.match(/<th scope="col"/g) ?? []).length, 3);
  assert.equal((html.match(/aria-sort="none"/g) ?? []).length, 3);
  assert.match(html, /<th scope="col" data-align="end" data-col="net" aria-sort="none"><button type="button" class="ds-grid-sort"><span class="ds-grid-head"><span class="ds-grid-head-label">Net<\/span><span class="ds-grid-unit">MWh<\/span><\/span>/);
  // The month merges over its hubs while the grid is in its own order.
  assert.match(html, /<th scope="rowgroup" rowSpan="2" data-align="start" data-col="month">2026-12<\/th>/);
  assert.equal((html.match(/data-col="month"/g) ?? []).length, 3, "header plus two merged groups");
  // A missing figure is a dash, never zero; a simulated one says so beside the value.
  assert.match(html, /data-col="net">–<\/td>/);
  assert.match(html, /<span class="ds-cell-mark" data-state="simulated" title="Simulated: not a market price"><span aria-hidden="true">sim<\/span><span class="ds-visually-hidden">Simulated: not a market price<\/span><\/span>/);
  // Not interactive: a plain table, no row in the Tab order.
  assert.doesNotMatch(html, /role="grid"/);
  assert.doesNotMatch(html, /<tr[^>]*tabindex/);
});

test("DataGrid: sorted, a column says so and the merge gives way", async () => {
  const Ui = await ui();
  const html = render(
    h(Ui.DataGrid<Row>, { label: "Position", columns: gridColumns(Ui), rows: ROWS, rowKey: (row: Row) => `${row.month}-${row.hub}`, defaultSort: { columnId: "net", direction: "descending" } }),
  );
  assert.match(html, /data-col="net" aria-sort="descending"><button type="button" class="ds-grid-sort" data-sorted="descending">/);
  const order = [...html.matchAll(/data-row-key="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(order, ["2026-12-NBP", "2026-12-TTF", "2027-01-NBP"]);
  assert.doesNotMatch(html, /rowSpan/);
});

test("DataGrid: rows with an action are a grid with one Tab stop and the selection marked", async () => {
  const Ui = await ui();
  const html = render(
    h(Ui.DataGrid<Row>, {
      label: "Hubs",
      columns: gridColumns(Ui),
      rows: ROWS,
      rowKey: (row: Row) => `${row.month}-${row.hub}`,
      selectedKey: "2026-12-TTF",
      onRowAction: () => undefined,
      density: "compact",
    }),
  );
  assert.match(html, /<table class="ds-grid ds-grid-compact ds-grid-interactive" role="grid" aria-label="Hubs">/);
  assert.equal((html.match(/<tr data-row-key="[^"]+" data-row-index="\d" tabindex="0"/g) ?? []).length, 1);
  assert.match(html, /data-row-key="2026-12-TTF" data-row-index="1" tabindex="0" aria-selected="true"/);
  assert.match(html, /data-row-key="2026-12-NBP" data-row-index="0" tabindex="-1" aria-selected="false"/);
});

test("DataGrid: loading shows skeleton rows, empty shows one line, 500 rows render without measuring", async () => {
  const Ui = await ui();
  const loading = render(h(Ui.DataGrid<Row>, { label: "Position", columns: gridColumns(Ui), rows: [], rowKey: (row: Row) => row.hub, loading: true, loadingLabel: "Loading the ladder" }));
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /<span class="ds-visually-hidden">Loading the ladder<\/span>/);
  const empty = render(h(Ui.DataGrid<Row>, { label: "Position", columns: gridColumns(Ui), rows: [], rowKey: (row: Row) => row.hub, empty: "No positions in the books you can see." }));
  assert.match(empty, /<td colSpan="3"><div class="empty-state empty-state-compact" role="status"><p><strong>No positions in the books you can see.<\/strong><\/p><\/div><\/td>/);
  const many: Row[] = Array.from({ length: 500 }, (_, index) => ({ hub: `H${index}`, month: `2027-${String((index % 12) + 1).padStart(2, "0")}`, net: index * 7 - 1000 }));
  const started = performance.now();
  const big = render(h(Ui.DataGrid<Row>, { label: "Many", columns: gridColumns(Ui), rows: many, rowKey: (row: Row) => row.hub, onRowAction: () => undefined, defaultSort: { columnId: "net", direction: "ascending" } }));
  const elapsed = performance.now() - started;
  assert.equal((big.match(/<tr data-row-key/g) ?? []).length, 500);
  assert.ok(elapsed < 1500, `500 rows rendered in ${elapsed.toFixed(0)} ms`);
  const source = readFileSync(new URL("../src/components/ui/DataGrid.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /getBoundingClientRect|offsetHeight|offsetWidth/, "no layout reads in the grid");
  const css = readFileSync(new URL("../src/components/ui/datagrid.css", import.meta.url), "utf8");
  assert.match(css, /\.ds-grid \[data-align="end"\] \{\s*text-align: right;\s*font-variant-numeric: var\(--ds-numeric\);/);
  assert.match(css, /@media \(prefers-reduced-motion: no-preference\) \{[\s\S]*\.ds-cell-flash\[data-flash="a"\]/, "the flash runs only when motion is allowed");
});

/* ----------------------------------------------------------------- Today */

const METHOD: RiskMethodNoteDTO = {
  key: "net_position",
  summary: "Net MWh per gas day.",
  includes: ["Physical contracts"],
  excludes: ["Flexibility"],
  params: {},
  inputs_as_of: { positions: "2026-11-15T00:00:00+00:00" },
  i18n: { summary: "risk.method.net_position.summary", includes: ["risk.method.net_position.includes.legs"], excludes: ["risk.method.net_position.excludes.flex"] },
  review_status: "drafted",
};

function figure(key: string, value: number | null, unit: string, extra: Record<string, unknown> = {}) {
  return { key, label: key, value, unit, as_of: "2026-11-14", state: "current", simulated: true, source: "Demo price", ...extra };
}

function todayFixture(): DeskTodayDTO {
  return {
    as_of: "2026-11-15T09:46:00+00:00",
    gas_day: "2026-11-15",
    front_month: "Dec-26",
    simulated: true,
    simulated_notice: "Demo data: simulated figures, not market data.",
    stale_figures: [],
    warnings: [],
    rows: [
      {
        key: "key_figures",
        title: "Key figures",
        populated: true,
        prices: [
          { ...figure("price.NBP", 33.662, "GBP/MWh"), hub: "NBP", product: "Dec-26", tenor: "month-ahead", close_day: "2026-11-14", day_change: -0.082, day_change_vs: "2026-11-13" },
          { key: "price.PEG", hub: "PEG", empty: { code: "no_close", reason: "No PEG close yet", action: "Import settlements" } },
        ],
        prices_empty: null,
        position: { today: { ...figure("position.net.today", 46000, "MWh/d", { simulated: false }), method: METHOD }, front_month: figure("position.net.front_month", 28516, "MWh/d", { label: "Net position Dec-26", simulated: false }) },
        position_empty: null,
        tightest_limit: null,
        limit_empty: { code: "LIMITS_NOT_ENTITLED_TO_ALL_BOOKS", reason: "Limits need every book behind them", action: "Ask risk for the limits view" },
      },
      {
        key: "changes",
        title: "What changed",
        populated: true,
        empty: null,
        alerts: { counts: { open: 0, critical: 0, warning: 0 }, items: [], more: 0, listed_elsewhere: 0 },
        outages: {
          counts: { active: 1, scheduled: 0, total: 1 },
          horizon_days: 14,
          as_of: "2026-11-15T09:46:00+00:00",
          state: "current",
          items: [{ event_id: "u1", facility: "Demo Haldor field", zone: "NBP", status: "active", start_utc: "2026-11-15T06:46:00Z", end_utc: null, unavailable: 563.2, unit: "GWh/d", as_of: null, simulated: true, why: { subject: "outage", id: "u1" } }],
          more: 0,
        },
      },
      { key: "book", title: "Book", populated: false, empty: { code: "NO_POSITIONS", reason: "No positions in the books you can see", action: "Add a contract" }, hubs: [] },
      {
        key: "fundamentals",
        title: "Fundamentals",
        populated: true,
        empty: null,
        storage: { latest: figure("storage.nwe.fill", 72.61, "%"), inventory_twh: 385.4, unit: "TWh", series: [] },
        balance: { empty: { code: "no_balance", reason: "No flows ingested", action: "Ingest ENTSOG flows" } },
      },
    ],
  } as unknown as DeskTodayDTO;
}

test("Today: four rows, simulated marked beside each value, empty sections give the reason and next step", async () => {
  const { load } = await loadApiStore();
  const { TodayScreen, TodayFreshness } = await load<typeof import("../src/components/TodayScreen.tsx")>("/src/components/TodayScreen.tsx");
  const props = {
    today: todayFixture(),
    loading: false,
    error: null,
    t,
    language: "en",
    nowMs: Date.parse("2026-11-15T10:00:00Z"),
    onRefresh: () => undefined,
    onOpenBrief: () => undefined,
    onOpenLimits: () => undefined,
    onOpenOutages: () => undefined,
  };
  const html = render(h(TodayScreen, props));
  for (const row of ["key_figures", "changes", "book", "fundamentals"]) assert.match(html, new RegExp(`data-today-row="${row}"`));
  assert.doesNotMatch(html, /Withheld/i);
  // The NBP price carries its unit and the simulated marker inside the value.
  assert.match(html, /<strong[^>]*>33\.662<small class="metric-strip-unit key-figure-unit">GBP\/MWh<\/small><span class="ds-cell-mark" data-state="simulated"/);
  assert.match(html, /today\.day_change\(change=−0\.082,day=13 Nov\)/);
  // A real (not simulated) figure carries no marker.
  assert.match(html, /<strong class="is-long"[^>]*>46,000<small class="metric-strip-unit key-figure-unit">MWh\/d<\/small><\/strong>/);
  // Empty sections: the server's reason and action in words; the code only for support.
  assert.match(html, /data-empty-code="LIMITS_NOT_ENTITLED_TO_ALL_BOOKS" title="LIMITS_NOT_ENTITLED_TO_ALL_BOOKS"/);
  assert.match(html, /<strong>Limits need every book behind them<\/strong><span> Ask risk for the limits view<\/span>/);
  assert.doesNotMatch(html.replace(/(title|data-empty-code)="[^"]*"/g, ""), /LIMITS_NOT_ENTITLED|NO_POSITIONS/);
  assert.match(html, /No positions in the books you can see/);
  // Outage: value, unit and the simulated marker beside it, and a Why.
  assert.match(html, /563<small class="ds-grid-unit">GWh\/d<\/small><span class="ds-cell-mark" data-state="simulated"/);
  assert.match(html, /aria-label="why\.label\(subject=Demo Haldor field\)"/);
  // Risk figures carry a Method affordance.
  assert.match(html, /data-method="net_position"/);
  // The demo desk says "Demo data" once; it does not shout stale.
  const fresh = render(h(TodayFreshness, { today: todayFixture(), t, nowMs: props.nowMs }));
  assert.match(fresh, /data-today-freshness="demo"/);
  assert.match(fresh, /today\.demo_data/);
  assert.doesNotMatch(fresh, /stale/);
  const live = { ...todayFixture(), simulated: false, stale_figures: [{ key: "price.NBP", label: "NBP Dec-26", state: "stale" as const, as_of: "2026-11-12" }] };
  const named = render(h(TodayFreshness, { today: live, t, nowMs: props.nowMs }));
  assert.match(named, /data-today-freshness="stale"/);
  assert.match(named, /today\.stale_link\(count=1\)/);
  assert.match(named, /aria-haspopup="dialog"/);
});

test("Method note: the reader's language when the build has the key, the server's sentence when not", async () => {
  const { load } = await loadApiStore();
  const { methodText } = await load<typeof import("../src/components/MethodNote.tsx")>("/src/components/MethodNote.tsx");
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const translate = (key: string) => en[key] ?? key;
  const text = methodText(METHOD, translate);
  assert.equal(text.summary, en["risk.method.net_position.summary"]);
  const missing = methodText({ ...METHOD, i18n: { summary: "risk.method.unknown.summary", includes: [], excludes: [] } }, translate);
  assert.equal(missing.summary, "Net MWh per gas day.");
  assert.deepEqual(missing.includes, ["Physical contracts"]);
});
