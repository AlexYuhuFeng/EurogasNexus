/**
 * Keystroke to answer for the answers the bar gives locally (conversions, arithmetic, the
 * glossary, a hub's palette results): each query typed one character at a time, the route, the
 * instant row and the palette's ordered results computed per keystroke, as the palette does.
 * The look-ups that read (a price, a spread, the portfolio) are not timed here: they run after
 * the debounce, or at once when their reads are held (`readsFor` in useAnswerBar).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { UnitsReferenceDTO } from "../src/api/client.ts";
import { HUBS } from "../src/app/answer/intent.ts";
import { instantAnswer } from "../src/app/answer/instant.ts";
import { routeQuery } from "../src/app/answer/route.ts";
import {
  filterPaletteCommands,
  glossaryCommands,
  hubCommands,
  navigationCommands,
  orderPaletteResults,
  type PaletteCommand,
} from "../src/app/experience/commandPalette.ts";

const UNITS = JSON.parse(readFileSync(new URL("./fixtures/unitsReference.json", import.meta.url), "utf8")) as UnitsReferenceDTO;
const FX = { source: "ECB", rates: { GBP: { rate: 0.85, date: "2026-11-13" }, USD: { rate: 1.08, date: "2026-11-13" } } };
// A glossary the size of the product's (a few hundred terms), NBP among them.
const GLOSSARY = Array.from({ length: 400 }, (_, index) => ({
  term: index === 0 ? "NBP" : `Term ${index}`, aliases: [`Alias ${index}`], definition_en: "A definition.",
}));
const QUERIES = [
  "800 GWh/d in MMBtu", "how many MMBtu is 800 GWh/d", "40 EUR/MWh to p/th", "(42.5-39.8)*30",
  "10 mcm to GWh at 11.2", "NBP", "NBP TTF spread", "what's my portfolio like", "storage DE", "what is NBP",
];

test("every keystroke answers locally in well under a frame", (t) => {
  const commands = [...navigationCommands(), ...glossaryCommands(GLOSSARY), ...hubCommands(HUBS)];
  const labelFor = (command: PaletteCommand) => command.label ?? command.labelKey;
  const context = { units: UNITS, fx: FX, glossary: GLOSSARY, bookAllowed: true, zh: false, now: new Date("2026-11-16T12:00:00Z") };
  // The work is measured, not the wall clock: on a loaded shared machine a keystroke can wait
  // for a core, which says nothing about the code. Each round's CPU time (this process's user +
  // system time, which does not run while the process is descheduled) is divided by its
  // keystrokes, and the median round is judged, so one round with a GC pause cannot fail it.
  const perKeystroke: number[] = [];
  for (let round = 0; round < 12; round += 1) {
    let keystrokes = 0;
    const cpuStart = process.cpuUsage();
    for (const query of QUERIES) {
      for (let length = 1; length <= query.length; length += 1) {
        const typed = query.slice(0, length);
        instantAnswer(routeQuery(typed, context));
        orderPaletteResults(filterPaletteCommands(commands, typed, labelFor, 100), typed, labelFor, ["navigate", "glossary", "inspect", "ai", "utility"]);
        keystrokes += 1;
      }
    }
    const cpu = process.cpuUsage(cpuStart);
    // The first two rounds warm the JIT.
    if (round >= 2) perKeystroke.push((cpu.user + cpu.system) / 1000 / keystrokes);
  }
  perKeystroke.sort((a, b) => a - b);
  const median = perKeystroke[Math.floor(perKeystroke.length / 2)];
  t.diagnostic(`CPU per keystroke over ${perKeystroke.length} rounds: median ${median.toFixed(3)} ms, worst round ${perKeystroke[perKeystroke.length - 1].toFixed(3)} ms`);
  // A frame is 16 ms; half a frame of CPU per keystroke leaves room for rendering.
  assert.ok(median < 8, `median ${median.toFixed(3)} ms of CPU per keystroke`);
  // The full query answers without Enter.
  assert.equal(instantAnswer(routeQuery("800 GWh/d in MMBtu", context))?.unit, "MMBtu/d");
});
