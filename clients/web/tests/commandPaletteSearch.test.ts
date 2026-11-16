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

test("each mode and each task is one distinct, correctly tagged result, in both languages", async () => {
  const { paletteLabel, paletteTagKey } = await import("../src/app/experience/commandPalette.ts");
  const { PRODUCT_MODES } = await import("../src/app/navigation/modeNavigation.ts");
  const { readFileSync } = await import("node:fs");
  for (const file of ["en", "zh"]) {
    const dict = JSON.parse(readFileSync(new URL(`../src/i18n/${file}.json`, import.meta.url), "utf8")) as Record<string, string>;
    const t = (key: string) => dict[key] ?? key;
    const commands = navigationCommands();
    assert.equal(PRODUCT_MODES.length, 4);
    for (const mode of PRODUCT_MODES) {
      const own = commands.filter((c) => c.id === `navigate.mode.${mode.id}` || c.id.startsWith(`navigate.mode.${mode.id}.`));
      const modeCommand = own.find((c) => c.id === `navigate.mode.${mode.id}`)!;
      assert.equal(modeCommand.kind, "mode");
      assert.equal(t(paletteTagKey(modeCommand)), file === "en" ? "Mode" : "模式");
      const tasks = own.filter((c) => c !== modeCommand);
      assert.equal(tasks.length, mode.tasks.length);
      for (const task of tasks) assert.equal(task.kind, "task", task.id);
      // What a reader sees (tag + label) is never the same twice within a mode.
      const shown = own.map((c) => `${t(paletteTagKey(c))}|${paletteLabel(c, t)}`);
      assert.equal(new Set(shown).size, shown.length, `${file} ${mode.id}: ${shown.join(", ")}`);
      // The mode and its first task, which open the same screen, read differently.
      assert.notEqual(paletteLabel(modeCommand, t), paletteLabel(tasks[0], t));
      for (const key of [paletteTagKey(modeCommand), paletteTagKey(tasks[0])]) assert.ok(dict[key], `${file} ${key}`);
    }
    // Searching a mode's name lists its name once as a mode.
    const deals = filterPaletteCommands(commands, file === "en" ? "deals" : "交易项目", (c) => paletteLabel(c, t));
    assert.equal(deals.filter((c) => c.kind === "mode").length, 1);
  }
});
