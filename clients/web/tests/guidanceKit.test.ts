import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { missingReadiness, READINESS_MAX_ITEMS } from "../src/components/ui/readinessModel.ts";

// CP-06 guidance kit (design basis H.1, H.2): a purpose line on every commercial task, a
// readiness checklist only when something is missing, empty states that say why.

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const en = JSON.parse(read("../src/i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;

/** Tasks being removed by another package (design basis I.1): no purpose line is written. */
const BEING_REMOVED = new Set(["deals.evaluate", "deals.optimise", "deals.routes", "research.strategies", "research.data", "research.assistant"]);

function modeTasks(): string[] {
  const source = read("../src/app/navigation/modeNavigation.ts");
  const tasks: string[] = [];
  let mode = "";
  for (const line of source.split("\n")) {
    const modeMatch = /^\s{4}id: "([a-z]+)",/.exec(line);
    if (modeMatch) mode = modeMatch[1];
    const taskMatch = /^\s{6}\{ id: "([a-z_-]+)"/.exec(line);
    if (taskMatch && mode) tasks.push(`${mode}.${taskMatch[1]}`);
  }
  return tasks;
}

test("every commercial task has a purpose line in both languages, at most 110 characters", () => {
  const tasks = modeTasks().filter((task) => !BEING_REMOVED.has(task));
  assert.ok(tasks.includes("desk.today") && tasks.includes("deals.review") && tasks.includes("book.limits"), tasks.join(","));
  for (const task of tasks) {
    for (const [name, table] of [["en", en], ["zh", zh]] as const) {
      const line = table[`purpose.${task}`];
      assert.ok(line, `${name}: purpose.${task} missing`);
      assert.ok(line.length <= 110, `${name}: purpose.${task} is ${line.length} characters`);
    }
  }
  assert.equal(en["purpose.desk.today"], "What changed since yesterday and what it means for your book.");
});

test("the purpose line is drawn by the one header every task uses", () => {
  assert.match(read("../src/app/navigation/useModeHeader.ts"), /purposeKey\(mode\?\.id \?\? null, location\?\.task\.id\)/);
  assert.match(read("../src/components/ui/WorkspaceHeader.tsx"), /<PageIntro purpose=\{purpose\} id=\{activeId\} \/>/);
  assert.match(read("../src/app/workspaces/WorkspaceRenderer.tsx"), /!usesConsolidatedHeader && <PageIntro purpose=\{mode\.purpose\}/);
  for (const file of ["MarketCockpit", "PortfolioWorkspace", "DecisionWorkspace"]) {
    assert.match(read(`../src/components/${file}.tsx`), /purpose=\{mode\.purpose\}/, file);
  }
  assert.match(read("../src/components/ui/PageIntro.tsx"), /data-purpose=/);
});

test("the readiness checklist shows only what is missing, at most three", () => {
  const items = [
    { id: "price", label: "price", ready: true },
    { id: "book", label: "book", ready: false },
    { id: "limits", label: "limits", ready: false },
    { id: "fx", label: "fx", ready: false },
    { id: "tariff", label: "tariff", ready: false },
  ];
  assert.deepEqual(missingReadiness(items).map((item) => item.id), ["book", "limits", "fx"]);
  assert.equal(READINESS_MAX_ITEMS, 3);
  assert.deepEqual(missingReadiness(items.slice(0, 1)), []);
});

test("an empty state for a permission names who grants it; a licence is connected, never bought", () => {
  assert.match(en["empty.permission"], /\{\{who\}\} grants it/);
  assert.match(en["empty.licence"], /administrator connects it/);
  assert.doesNotMatch(en["empty.licence"], /buy|purchase|upgrade/i);
  assert.match(read("../src/components/ui/EmptyState.tsx"), /data-empty-need=\{need\}/);
});


test("one purpose line per page: no page draws its own beside the shell's", async () => {
  const { readdirSync, statSync } = await import("node:fs");
  const root = new URL("../src/components/", import.meta.url);
  const offenders: string[] = [];
  const walk = (dir: URL) => {
    for (const name of readdirSync(dir)) {
      const path = new URL(name, dir);
      if (statSync(path).isDirectory()) walk(new URL(`${name}/`, dir));
      else if (name.endsWith(".tsx") && name !== "PageIntro.tsx" && /data-purpose=/.test(read(path.href.replace(/^.*\/src\//, "../src/")))) offenders.push(name);
    }
  };
  walk(root);
  assert.deepEqual(offenders, []);
  assert.equal(en["purpose.research.spreads"], "How one price trades against another, and whether moving gas between them pays.");
});
