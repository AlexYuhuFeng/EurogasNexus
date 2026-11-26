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
  assert.match(read("../src/app/navigation/useModeHeader.ts"), /purposeKey\(location\?\.mode\.id \?\? null, location\?\.task\.id\)/);
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

test("first-use hints: at most three a page, once per person, replayable, off for the sweep", async () => {
  const { hintsToShow, parseSeen, serialiseSeen, replayPage, MAX_HINTS_PER_PAGE } = await import("../src/components/ui/firstUseHintsModel.ts");
  const { FIRST_USE_HINTS } = await import("../src/app/experience/firstUseHints.ts");
  for (const [page, hints] of Object.entries(FIRST_USE_HINTS)) {
    assert.ok(hints.length <= MAX_HINTS_PER_PAGE, page);
    for (const hint of hints) {
      assert.ok(hint.id.startsWith(`${page}.`), hint.id);
      assert.ok(en[hint.textKey] && zh[hint.textKey], hint.textKey);
      assert.ok(en[hint.textKey].length <= 110, hint.textKey);
    }
  }
  const today = FIRST_USE_HINTS["desk.today"];
  assert.deepEqual(hintsToShow(today, parseSeen("")).map((hint) => hint.id), today.map((hint) => hint.id));
  assert.deepEqual(hintsToShow(today, parseSeen("desk.today.name")).map((hint) => hint.id), ["desk.today.feeds", "desk.today.brief"]);
  assert.deepEqual(hintsToShow(today, parseSeen(""), { off: true }), []);
  const seen = parseSeen("desk.today.name,deals.contracts.import");
  assert.equal(serialiseSeen(replayPage(seen, "desk.today")), "deals.contracts.import");
  assert.equal(serialiseSeen(["b", "a", "b"]), "a,b");
});

test("see an example: bundled, labelled as examples, never stored records", async () => {
  const { EXAMPLE_CONTRACTS, exampleOpportunityList, examplePositionLadder, exampleReports } = await import("../src/app/experience/examples.ts");
  const { readFileSync } = await import("node:fs");
  const now = new Date("2026-11-19T08:00:00Z");
  const ids = [
    ...EXAMPLE_CONTRACTS.map((row) => row.contract_id),
    ...Object.values(exampleOpportunityList(now).lanes).flatMap((bucket) => bucket?.items.map((row) => row.opportunity_id) ?? []),
    ...exampleReports(now).map((row) => row.report_id),
  ];
  assert.ok(ids.length >= 10);
  for (const id of ids) assert.match(id, /^example-/);
  for (const row of EXAMPLE_CONTRACTS) assert.match(row.contract_name, /^Example /);
  const ladder = examplePositionLadder(now);
  assert.equal(ladder.totals.net_mwh, ladder.rows.reduce((total, row) => total + row.net_mwh, 0));
  assert.ok(ladder.rows.every((row) => row.month > "2026-11"));
  const kit = readFileSync(new URL("../src/components/ui/ExampleView.tsx", import.meta.url), "utf8");
  assert.match(kit, /inert/);
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  for (const key of ["example.see", "example.banner", "example.banner_detail", "example.leave"]) assert.ok(en[key] && zh[key], key);
});
