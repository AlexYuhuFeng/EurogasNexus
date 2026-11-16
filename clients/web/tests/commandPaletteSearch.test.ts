/** The command palette finds glossary terms by name or alias, lists a destination once and shows its shortcut (#34). */
import assert from "node:assert/strict";
import test from "node:test";
import {
  filterPaletteCommands,
  glossaryCommands,
  navigationCommands,
  paletteShortcut,
  type PaletteCommand,
} from "../src/app/experience/commandPalette.ts";

const labels: Record<string, string> = {
  "nav.primary.market": "Market",
  "nav.market": "Market",
  "nav.network": "Network",
  "nav.mode.desk": "Desk",
  "nav.mode.desk.prices": "Prices",
  "nav.mode.book": "Book",
  "nav.mode.book.limits": "Limits & P&L",
  "nav.mode.deals": "Deals",
  "portfolio.task.exposure": "Exposure",
  "nav.primary.decision": "Decision Center",
  "nav.primary.portfolio": "Portfolio",
};
const labelFor = (command: PaletteCommand) =>
  command.label ??
  [command.labelKey, command.subLabelKey].filter(Boolean).map((key) => labels[key!] ?? key).join(" · ");

test("a glossary term is found by its name and by an alias, never for an empty query", () => {
  const terms = glossaryCommands([
    { term: "NBP", aliases: ["National Balancing Point"] },
    { term: "TTF", aliases: ["Title Transfer Facility"] },
  ]);
  const all = [...navigationCommands(), ...terms];
  assert.deepEqual(filterPaletteCommands(all, "nbp", labelFor).map((c) => c.id), ["glossary.NBP"]);
  assert.deepEqual(filterPaletteCommands(all, "title transfer", labelFor).map((c) => c.id), ["glossary.TTF"]);
  assert.ok(!filterPaletteCommands(all, "", labelFor).some((c) => c.group === "glossary"));
  assert.equal(terms[0].target.term, "NBP");
});

test("a mode and its first task under the same name are one result each; old names are aliases (WF-05)", () => {
  const desk = filterPaletteCommands(navigationCommands(), "desk", labelFor);
  assert.equal(desk.filter((c) => labelFor(c) === "Desk").length, 1);
  // The old area and task names still find the new destinations.
  const aliases = (command: PaletteCommand) => (command.aliasKeys ?? []).map((key) => labels[key] ?? key);
  const market = filterPaletteCommands(navigationCommands(), "market", labelFor, 50, aliases).map((c) => c.id);
  assert.ok(market.includes("navigate.mode.desk"), market.join(","));
  assert.ok(filterPaletteCommands(navigationCommands(), "decision center", labelFor, 50, aliases).some((c) => c.id === "navigate.mode.deals"));
  assert.ok(filterPaletteCommands(navigationCommands(), "exposure", labelFor, 50, aliases).some((c) => c.id === "navigate.mode.book.limits"));
  assert.ok(filterPaletteCommands(navigationCommands(), "portfolio", labelFor, 50, aliases).some((c) => c.id === "navigate.mode.book"));
  // No page of a mode is listed under its old technical name.
  assert.ok(!navigationCommands().some((c) => c.id === "navigate.page.market" || c.id === "navigate.primary.decision"));
});

test("modes show the shortcut the key handler binds", () => {
  const [first] = navigationCommands();
  assert.equal(first.id, "navigate.mode.desk");
  assert.equal(paletteShortcut(first, false), "Ctrl+Shift+1");
  assert.equal(paletteShortcut(first, true), "⌘+Shift+1");
  assert.equal(paletteShortcut(navigationCommands().find((c) => c.id === "navigate.mode.research")!, false), "Ctrl+Shift+4");
  assert.equal(paletteShortcut(navigationCommands().find((c) => c.id === "navigate.primary.administration")!, false), "Ctrl+Shift+6");
  assert.equal(paletteShortcut(navigationCommands().find((c) => c.id === "navigate.mode.book.limits")!, false), null);
});

test("a sub-view is found by the words of its page and its view (#31)", () => {
  const found = filterPaletteCommands(navigationCommands(), "nav.runtime runtime.view.deliv", labelFor);
  assert.ok(found.some((command) => command.id === "navigate.view.runtime.delivery"));
});
