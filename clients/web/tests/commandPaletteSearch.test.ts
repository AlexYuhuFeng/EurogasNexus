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

const labels: Record<string, string> = { "nav.primary.market": "Market", "nav.market": "Market", "nav.network": "Network" };
const labelFor = (command: PaletteCommand) => command.label ?? labels[command.labelKey] ?? command.labelKey;

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

test("a primary and the page it opens under the same name are one result", () => {
  const market = filterPaletteCommands(navigationCommands(), "market", labelFor);
  assert.equal(market.filter((c) => labelFor(c) === "Market").length, 1);
});

test("primary workspaces show the shortcut the key handler binds", () => {
  const [first] = navigationCommands();
  assert.equal(paletteShortcut(first, false), "Ctrl+Shift+1");
  assert.equal(paletteShortcut(first, true), "⌘+Shift+1");
  assert.equal(paletteShortcut(navigationCommands().find((c) => c.id === "navigate.page.network")!, false), null);
});
