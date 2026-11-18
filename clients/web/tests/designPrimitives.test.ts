/**
 * UX-02 primitives: Button, IconButton, StatusBadge, KeyFigure, Panel, EmptyState, Skeleton.
 * Each is rendered through the project's Vite pipeline and checked for its accessible name, its
 * keyboard behaviour (native buttons, explicit types, no focus traps) and the classes the token
 * stylesheet keys on.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

type Ui = typeof import("../src/components/ui/index.ts");

async function ui(): Promise<Ui> {
  const { load } = await loadApiStore();
  return load<Ui>("/src/components/ui/index.ts");
}

const h = React.createElement;
const render = (element: React.ReactElement) => renderToStaticMarkup(element);

test("Button: a native button, typed, with the variant's class and height", async () => {
  const { Button } = await ui();
  const html = render(h(Button, { variant: "primary", size: "md" }, "Save terms"));
  assert.match(html, /^<button type="button" class="ds-button button-primary ds-size-md">Save terms<\/button>$/);
  // Secondary and small by default; never submits a form by accident.
  assert.match(render(h(Button, null, "Add")), /type="button" class="ds-button secondary-button ds-size-sm"/);
  assert.match(render(h(Button, { variant: "quiet" }, "Refresh")), /quiet-button/);
  assert.match(render(h(Button, { variant: "danger" }, "Retire")), /class="ds-button danger ds-size-sm"/);
  assert.match(render(h(Button, { type: "submit" }, "Send")), /type="submit"/);
});

test("Button: loading is busy and cannot be pressed twice; disabled stays disabled", async () => {
  const { Button } = await ui();
  const busy = render(h(Button, { loading: true }, "Analyse"));
  assert.match(busy, /disabled=""/);
  assert.match(busy, /aria-busy="true"/);
  assert.match(busy, /data-loading=""/);
  assert.match(busy, />Analyse</, "the label stays, so the width does not jump");
  const off = render(h(Button, { disabled: true }, "Save"));
  assert.match(off, /disabled=""/);
  assert.doesNotMatch(off, /aria-busy/);
  assert.doesNotMatch(off, /tabindex/i, "a button is reachable by Tab without a tabindex");
});

test("IconButton: the label is the accessible name and the tooltip; the glyph is hidden", async () => {
  const { IconButton } = await ui();
  const html = render(h(IconButton, { label: "Close", icon: "×" }));
  assert.match(html, /aria-label="Close"/);
  assert.match(html, /title="Close"/);
  assert.match(html, /<span class="ds-icon" aria-hidden="true">×<\/span>/);
  assert.match(html, /class="ds-button quiet-button ds-size-sm ds-icon-button"/);
  // An explicit tooltip may differ from the name; the name never disappears.
  assert.match(render(h(IconButton, { label: "Help", icon: "?", title: "Report a problem" })), /aria-label="Help"[^>]*title="Report a problem"/);
});

test("StatusBadge: a tone carries a colour role and the state in words", async () => {
  const { StatusBadge } = await ui();
  for (const tone of ["ok", "watch", "breach", "info", "simulated", "stale", "neutral"] as const) {
    const html = render(h(StatusBadge, { tone }, `state ${tone}`));
    assert.match(html, new RegExp(`<span class="status-badge ds-status" data-tone="${tone}">state ${tone}</span>`));
  }
  // The domain form keeps its class family for existing call sites.
  assert.equal(
    render(h(StatusBadge, { variant: "job-state", status: "SUCCEEDED" }, "Done")),
    '<span class="job-state job-state-succeeded">Done</span>',
  );
  const css = readFileSync(new URL("../src/components/ui/primitives.css", import.meta.url), "utf8");
  for (const tone of ["ok", "watch", "breach", "info", "simulated", "stale"]) {
    assert.match(css, new RegExp(`\\.ds-status\\[data-tone="${tone}"\\] \\{ background: var\\(--ds-status-${tone}-soft\\); color: var\\(--ds-status-${tone}\\); \\}`));
  }
});

test("KeyFigure: labelled group, value then unit, delta by the P&L convention, state in words", async () => {
  const { KeyFigure } = await ui();
  const html = render(
    h(KeyFigure, {
      label: "Net",
      value: "+16,606,000",
      unit: "MWh",
      delta: { text: "+12,000", value: 12000 },
      age: "2 min",
      state: "stale",
      stateLabel: "Stale",
    }),
  );
  const labelId = /<span id="([^"]+)">Net<\/span>/.exec(html)?.[1];
  assert.ok(labelId, "the label has an id");
  assert.match(html, new RegExp(`role="group" aria-labelledby="${labelId}"`));
  assert.match(html, /data-state="stale"/);
  assert.match(html, /<strong>\+16,606,000<small class="metric-strip-unit key-figure-unit">MWh<\/small><\/strong>/);
  assert.match(html, /<small class="key-figure-delta pnl-profit">\+12,000<\/small>/);
  assert.match(html, /<span class="key-figure-state">Stale<\/span><span>2 min<\/span>/);
  // A current figure with no age says nothing extra; a missing value is a dash, never zero.
  const plain = render(h(KeyFigure, { label: "VaR", value: "–" }));
  assert.doesNotMatch(plain, /data-state|key-figure-age|key-figure-delta/);
  assert.match(render(h(KeyFigure, { label: "MtM", value: "1", size: "lg" })), /class="key-figure key-figure-lg"/);
  const css = readFileSync(new URL("../src/components/ui/primitives.css", import.meta.url), "utf8");
  assert.match(css, /\.key-figure > strong \{[^}]*font-variant-numeric: var\(--ds-numeric\);/);
});

test("Panel: the section is named by its title; actions share the title row", async () => {
  const { Panel, Button } = await ui();
  const html = render(
    h(Panel, { title: "Major hub board", actions: h(Button, { variant: "quiet" }, "Refresh"), meta: "EUR/MWh" }, h("p", null, "body")),
  );
  const headingId = /<h2 id="([^"]+)">Major hub board<\/h2>/.exec(html)?.[1];
  assert.ok(headingId);
  assert.match(html, new RegExp(`^<section class="workspace-panel ds-panel" aria-labelledby="${headingId}">`));
  assert.match(html, /<div class="panel-title-row ds-panel-head"><h2[^>]*>Major hub board<\/h2><span class="ds-panel-meta">EUR\/MWh<\/span><div class="ds-panel-actions"><button/);
  assert.match(html, /<div class="ds-panel-body"><p>body<\/p><\/div><\/section>$/);
  assert.match(render(h(Panel, { title: "Sub", level: 3 }, "x")), /<h3 id=/);
});

test("EmptyState: one line with the cause, the next step and at most one action", async () => {
  const { EmptyState, Button } = await ui();
  const html = render(
    h(EmptyState, { reason: "No storage data.", next: "Appears after GIE AGSI is ingested.", action: h(Button, null, "Connect"), id: "storage" }),
  );
  assert.match(html, /^<div class="empty-state" role="status" data-empty-state="storage"><p><strong>No storage data\.<\/strong><span> Appears after GIE AGSI is ingested\.<\/span><\/p><button/);
  assert.match(render(h(EmptyState, { reason: "Nothing.", compact: true })), /class="empty-state empty-state-compact"/);
});

test("Skeleton: one announced loading status; the bars are hidden from assistive technology", async () => {
  const { Skeleton } = await ui();
  const html = render(h(Skeleton, { label: "Loading the position ladder", rows: 3 }));
  assert.match(html, /^<div class="ds-skeleton-group" role="status" aria-busy="true" aria-live="polite"><span class="ds-visually-hidden">Loading the position ladder<\/span>/);
  assert.equal((html.match(/class="ds-skeleton ds-skeleton-row" aria-hidden="true"/g) ?? []).length, 3);
  assert.equal((render(h(Skeleton, { label: "x", rows: 0, variant: "text" })).match(/ds-skeleton-text/g) ?? []).length, 1);
});

test("primitives are adopted at real call sites", () => {
  const read = (file: string) => readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
  const uses: Array<[string, RegExp]> = [
    ["components/TodayScreen.tsx", /<Button variant="quiet"/],
    ["components/DealHedgeApprovalsPanel.tsx", /<Button variant="secondary"/],
    ["components/DeskBriefDialog.tsx", /<Dialog\s/],
    ["components/DeskBriefDialog.tsx", /<Segmented\s/],
    ["components/ReportProblemDialog.tsx", /<Dialog\s/],
    ["components/ReportProblemDialog.tsx", /<Field label=/],
    ["components/KeyboardShortcutsDialog.tsx", /<Dialog open=\{open\}/],
    ["components/InspectorPanel.tsx", /<Sheet\s/],
    ["components/WhyButton.tsx", /<Popover\s/],
    ["components/MethodNote.tsx", /<Popover\s/],
    ["components/ProjectionContextStrip.tsx", /<Popover\s/],
    ["components/CapacityWorkspace.tsx", /<Segmented\s/],
    ["components/NetworkWorkspace.tsx", /<Segmented\s/],
    ["components/PositionLadderPanel.tsx", /<Toolbar\s/],
    ["components/PositionLadderPanel.tsx", /<DataGrid\s/],
    ["components/RiskLimitsPanel.tsx", /<DataGrid\s/],
    ["components/NweBalancePanel.tsx", /<DataGrid\s/],
    ["components/TodayScreen.tsx", /<DataGrid\s/],
    ["components/ReportProblemDialog.tsx", /<Dialog\s/],
    ["components/AlertCenter.tsx", /<IconButton label=/],
    ["components/MarketTerminal.tsx", /<StatusBadge tone="simulated"/],
    ["components/PositionLadderPanel.tsx", /<KeyFigure label=\{t\("position\.net"\)\}/],
    ["components/TodayScreen.tsx", /<KeyFigure\s/],
    ["components/ui/MetricStrip.tsx", /<KeyFigure /],
    ["components/TodayScreen.tsx", /<Panel\s+title=\{t\("today\.alerts"\)\}/],
    ["components/TodayScreen.tsx", /<EmptyState compact reason=\{t\("today\.no_alerts"\)\}/],
    ["components/PositionLadderPanel.tsx", /<EmptyState reason=\{t\("position\.empty"\)\}/],
    ["components/PositionLadderPanel.tsx", /<Skeleton label=\{t\("position\.loading"\)\}/],
  ];
  for (const [file, pattern] of uses) assert.match(read(file), pattern, file);
});
