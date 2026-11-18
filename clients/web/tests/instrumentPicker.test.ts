/**
 * InstrumentPicker (design basis 2, D.2): the search grammar (EN and ZH, table-driven), presets,
 * the twelve-item cap per level, recent picks, the keyboard path through the pure reducer, and
 * the rendered combobox/listbox semantics.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  CLOSED,
  MAX_RECENT,
  MAX_VISIBLE,
  absoluteCodes,
  catalogueFromDTO,
  catalogueFromHubs,
  enterHub,
  hubKinds,
  pickerKey,
  pickerOptions,
  presetInstrument,
  readRecent,
  searchCatalogue,
  selectionOf,
  withQuery,
  withRecent,
  writeRecent,
  type PickerState,
} from "../src/app/model/instrumentPicker.ts";
import { fixtureCatalogue } from "../src/stories/instrumentPickerFixture.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const TODAY = new Date("2026-11-17T12:00:00Z");
const CATALOGUE = catalogueFromDTO(fixtureCatalogue(TODAY));

function first(query: string): string | null {
  const result = searchCatalogue(query, CATALOGUE, { today: TODAY })[0];
  if (!result) return null;
  return result.kind === "hub" ? `hub:${result.hub.hub}` : result.instrument.id;
}

test("search grammar resolves desk shorthand, English and Chinese", () => {
  const cases: Array<[string, string | null]> = [
    ["ttf jan27", "TTF:Jan-27"],
    ["TTF Jan-27", "TTF:Jan-27"],
    ["ttf january 2027", "TTF:Jan-27"],
    ["nbp m+1", "NBP:M+1"],
    ["NBP M + 1", "NBP:M+1"],
    ["the q1-27", "THE:Q1-27"],
    ["ztp da", "ZTP:DA"],
    ["peg cal-27", "PEG:Cal-27"],
    ["ttf win-27", "TTF:Win-27"],
    ["ttf sum 27", "TTF:Sum-27"],
    ["henry hub spot", "HH:Spot"],
    ["hh da", "HH:Spot"],
    ["ttf front month", "TTF:M+1"],
    ["nbp", "hub:NBP"],
    ["dutch", "hub:TTF"],
    // Chinese: country names for hubs, the product grammar for tenors.
    ["荷兰 27年1月", "TTF:Jan-27"],
    ["英国 次月", "NBP:M+1"],
    ["英国次月", "NBP:M+1"],
    ["德国 27年一季度", "THE:Q1-27"],
    ["比利时 日前", "ZTP:DA"],
    ["法国 27年日历年", "PEG:Cal-27"],
    ["荷兰 27年冬季", "TTF:Win-27"],
    ["荷兰", "hub:TTF"],
    // Nothing held, or not a tenor: no answer rather than a guess.
    ["psv jan27", null],
    ["ttf jan35", null],
    ["xyz", null],
  ];
  const wrong = cases
    .map(([query, expected]) => [query, expected, first(query)] as const)
    .filter(([, expected, got]) => expected !== got)
    .map(([query, expected, got]) => `${query}: got ${got}, wanted ${expected}`);
  assert.deepEqual(wrong, []);
});

test("a tenor alone finds it at every hub that holds it; a relative code finds the month it delivers", () => {
  const jan = searchCatalogue("jan27", CATALOGUE, { today: TODAY }).map((r) => (r.kind === "instrument" ? r.instrument.id : r.hub.hub));
  assert.deepEqual(jan, ["TTF:Jan-27", "NBP:Jan-27", "THE:Jan-27", "PEG:Jan-27", "ZTP:Jan-27"]);
  assert.deepEqual(absoluteCodes("M+1", TODAY), ["Dec-26"]);
  assert.deepEqual(absoluteCodes("Q+1", TODAY), ["Q1-27"]);
  assert.deepEqual(absoluteCodes("S+1", TODAY), ["Sum-27"]);
  assert.deepEqual(absoluteCodes("Cal+1", TODAY), ["Cal-27"]);
  // PEG holds no rolling M+2, but holds the month it delivers today.
  assert.equal(first("peg m+2"), "PEG:Jan-27");
});

test("presets resolve to what the hub holds", () => {
  const ttf = CATALOGUE.hubs.find((hub) => hub.hub === "TTF")!;
  assert.equal(presetInstrument(ttf, "front_month", TODAY)?.id, "TTF:M+1");
  assert.equal(presetInstrument(ttf, "next_quarter", TODAY)?.id, "TTF:Q1-27");
  assert.equal(presetInstrument(ttf, "next_season", TODAY)?.id, "TTF:Sum-27");
  assert.equal(presetInstrument(ttf, "next_cal", TODAY)?.id, "TTF:Cal-27");
  assert.equal(presetInstrument(ttf, "day_ahead", TODAY)?.id, "TTF:DA");
  const hh = CATALOGUE.hubs.find((hub) => hub.hub === "HH")!;
  assert.equal(presetInstrument(hh, "day_ahead", TODAY)?.id, "HH:Spot");
  assert.equal(presetInstrument(hh, "front_month", TODAY), null);
});

test("no level shows more than twelve items; the rest is counted and reached by search", () => {
  const ttf = CATALOGUE.hubs.find((hub) => hub.hub === "TTF")!;
  const level2: PickerState = { ...enterHub({ ...CLOSED, open: true }, ttf), kind: "month" };
  const { options, hidden } = pickerOptions(level2, CATALOGUE, { today: TODAY });
  assert.equal(options.length, MAX_VISIBLE);
  assert.equal(hidden, 18 - MAX_VISIBLE);
  assert.equal(first("ttf may28"), "TTF:May-28"); // the 18th month, beyond the visible twelve
  for (const hub of CATALOGUE.hubs) {
    for (const kind of hubKinds(hub)) {
      const shown = pickerOptions({ ...enterHub({ ...CLOSED, open: true }, hub), kind }, CATALOGUE, { today: TODAY }).options;
      assert.ok(shown.length <= MAX_VISIBLE, `${hub.hub} ${kind}`);
    }
  }
  const level1 = pickerOptions({ ...CLOSED, open: true }, CATALOGUE, { today: TODAY }).options;
  assert.ok(level1.length <= MAX_VISIBLE);
  assert.deepEqual(level1.map((o) => o.id), ["hub:TTF", "hub:NBP", "hub:THE", "hub:PEG", "hub:ZTP", "hub:HH"]);
});

test("recent picks head level 1 and are kept in browser storage, failures ignored", () => {
  const recent = withRecent(withRecent([], "NBP:M+1"), "TTF:Jan-27");
  assert.deepEqual(recent, ["TTF:Jan-27", "NBP:M+1"]);
  assert.equal(withRecent(["a", "b", "c", "d", "e"], "f").length, MAX_RECENT);
  const level1 = pickerOptions({ ...CLOSED, open: true }, CATALOGUE, { today: TODAY, recent }).options;
  assert.deepEqual(level1.slice(0, 4).map((o) => o.id), ["recent:TTF:Jan-27", "recent:NBP:M+1", "hub:TTF", "hub:NBP"]);
  const store = new Map<string, string>();
  const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
  writeRecent(storage, recent);
  assert.deepEqual(readRecent(storage), recent);
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(readRecent(broken), []);
  writeRecent(broken, recent); // does not throw
});

test("keyboard path: type a hub, Enter, change kind with arrows, move, Enter picks", () => {
  let state: PickerState = { ...CLOSED, open: true };
  const press = (key: string) => {
    const options = pickerOptions(state, CATALOGUE, { today: TODAY }).options;
    const hub = state.level === "tenor" ? CATALOGUE.hubs.find((item) => item.hub === state.hub) ?? null : null;
    const result = pickerKey(state, key, { options, kinds: hubKinds(hub) });
    state = result.state;
    if (result.effect.type === "choose") {
      const selection = selectionOf(result.effect.option, "instrument");
      if (!selection) state = enterHub(state, result.effect.option.hub);
      return selection;
    }
    return result.effect.type === "close" ? "closed" : null;
  };
  state = withQuery(state, "nbp");
  assert.equal(press("Enter"), null); // a hub opens its tenors
  assert.equal(state.level, "tenor");
  assert.equal(state.hub, "NBP");
  assert.equal(state.kind, "spot");
  press("ArrowRight");
  assert.equal(state.kind, "rolling");
  press("ArrowRight");
  assert.equal(state.kind, "month");
  press("ArrowLeft");
  press("ArrowRight");
  press("ArrowDown");
  press("ArrowDown");
  assert.equal(state.active, 2);
  press("End");
  assert.equal(state.active, 11);
  press("Home");
  const picked = press("Enter");
  assert.ok(picked && typeof picked === "object");
  assert.equal(picked.instrument?.id, "NBP:Dec-26");
  // Escape: clears the text, then back to hubs, then closes.
  state = withQuery(enterHub({ ...CLOSED, open: true }, CATALOGUE.hubs[0]), "jan");
  press("Escape");
  assert.equal(state.query, "");
  press("Escape");
  assert.equal(state.level, "hub");
  assert.equal(press("Escape"), "closed");
  assert.equal(state.open, false);
  // Backspace in an empty box at level 2 goes back to the hubs; with text it edits the text.
  state = enterHub({ ...CLOSED, open: true }, CATALOGUE.hubs[0]);
  press("Backspace");
  assert.equal(state.level, "hub");
  // Type-ahead straight to an instrument from level 1.
  state = withQuery({ ...CLOSED, open: true }, "the q1-27");
  const direct = press("Enter");
  assert.equal(direct && typeof direct === "object" ? direct.instrument?.id : null, "THE:Q1-27");
});

test("hub scope picks a hub on Enter and never offers tenors", () => {
  const hubs = catalogueFromHubs([{ hub: "TTF", nativeUnit: "EUR/MWh" }, { hub: "NBP", nativeUnit: "GBp/th" }]);
  const options = pickerOptions({ ...CLOSED, open: true }, hubs, { scope: "hub" }).options;
  assert.deepEqual(options.map((o) => o.id), ["hub:TTF", "hub:NBP"]);
  assert.deepEqual(selectionOf(options[1], "hub"), { hub: "NBP", instrument: null });
  const searched = pickerOptions(withQuery({ ...CLOSED, open: true }, "英国"), hubs, { scope: "hub" }).options;
  assert.deepEqual(searched.map((o) => o.id), ["hub:NBP"]);
});

test("rendered picker: a combobox over a listbox, at most twelve options, sim marked, tokens only", async () => {
  const harness = await loadApiStore();
  const { InstrumentPicker } = await harness.load<typeof import("../src/components/ui/InstrumentPicker.tsx")>(
    "/src/components/ui/InstrumentPicker.tsx",
  );
  const closed = renderToStaticMarkup(React.createElement(InstrumentPicker, {
    catalogue: CATALOGUE, value: "THE:M+1", onChange: () => {}, label: "Leg 1", today: TODAY,
  }));
  assert.match(closed, /aria-haspopup="dialog" aria-expanded="false"/);
  assert.match(closed, /THE M\+1/);
  assert.match(closed, /class="ds-ipicker-sim"/);
  assert.doesNotMatch(closed, /role="listbox"/);
  const open = renderToStaticMarkup(React.createElement(InstrumentPicker, {
    catalogue: CATALOGUE, value: null, onChange: () => {}, label: "Leg 1", today: TODAY, defaultOpen: true,
  }));
  assert.match(open, /role="dialog" aria-label="Leg 1"/);
  assert.match(open, /role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="[^"]+-list" aria-activedescendant="[^"]+"/);
  assert.match(open, /role="listbox"/);
  const optionCount = (open.match(/role="option"/g) ?? []).length;
  assert.ok(optionCount > 0 && optionCount <= MAX_VISIBLE, `${optionCount} options`);
  assert.equal((open.match(/aria-selected="true"/g) ?? []).length, 1);
  const empty = renderToStaticMarkup(React.createElement(InstrumentPicker, {
    catalogue: { hubs: [] }, value: null, onChange: () => {}, label: "Leg 1", defaultOpen: true,
  }));
  assert.match(empty, /instrument_picker\.no_series/);
  const css = readFileSync(new URL("../src/components/ui/instrumentPicker.css", import.meta.url), "utf8");
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b|rgba?\(/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*position: fixed/);
});

test("multi-select hub picker: the board's hubs ticked, a listbox that says it is multi-select", async () => {
  const harness = await loadApiStore();
  const { InstrumentPicker } = await harness.load<typeof import("../src/components/ui/InstrumentPicker.tsx")>(
    "/src/components/ui/InstrumentPicker.tsx",
  );
  const hubs = catalogueFromHubs([{ hub: "TTF", nativeUnit: "EUR/MWh" }, { hub: "NBP", nativeUnit: "GBp/th" }, { hub: "THE", nativeUnit: "EUR/MWh" }]);
  const html = renderToStaticMarkup(React.createElement(InstrumentPicker, {
    catalogue: hubs, value: null, onChange: () => {}, label: "Hubs", scope: "hub", defaultOpen: true,
    multiSelected: ["TTF", "THE"], triggerLabel: "2 hubs",
  }));
  assert.match(html, /aria-multiselectable="true"/);
  assert.equal((html.match(/aria-selected="true"/g) ?? []).length, 2);
  assert.equal((html.match(/data-ticked="true"/g) ?? []).length, 2);
  assert.match(html, /2 hubs/);
});
