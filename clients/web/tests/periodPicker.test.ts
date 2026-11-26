import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  clampDay,
  dayKey,
  monthGrid,
  moveDay,
  parseDay,
  parseMonth,
  periodText,
  weekdayLabels,
  withTime,
} from "../src/components/ui/periodModel.ts";

// The PeriodPicker (DESIGN_TOKENS "PeriodPicker"): the app's own date control, in the app's
// language, replacing native inputs whose text follows the device ("2026年12月" in English).

test("the calendar is Monday-first and covers the month", () => {
  const weeks = monthGrid(2026, 11); // 1 Nov 2026 is a Sunday
  assert.equal(weeks[0]!.filter(Boolean).length, 1);
  assert.equal(weeks[0]![6]!.day, 1);
  assert.equal(weeks.flat().filter(Boolean).length, 30);
  assert.ok(weeks.every((week) => week.length === 7));
});

test("keys move like a date-picker grid", () => {
  const day = { year: 2026, month: 11, day: 30 };
  assert.equal(dayKey(moveDay(day, "ArrowRight")!), "2026-12-01");
  assert.equal(dayKey(moveDay(day, "ArrowUp")!), "2026-11-23");
  assert.equal(dayKey(moveDay(day, "Home")!), "2026-11-30"); // a Monday
  assert.equal(dayKey(moveDay(day, "End")!), "2026-12-06");
  assert.equal(dayKey(moveDay({ year: 2027, month: 1, day: 31 }, "PageDown")!), "2027-02-28");
  assert.equal(dayKey(moveDay(day, "PageUp", true)!), "2025-11-30");
  assert.equal(moveDay(day, "Tab"), null);
  assert.equal(dayKey(clampDay(day, "2026-12-05")), "2026-12-05");
});

test("values keep the native strings and the text follows the app's language", () => {
  assert.equal(parseDay("2026-02-30"), null);
  assert.deepEqual(parseMonth("2026-12"), { year: 2026, month: 12 });
  assert.equal(periodText("month", "2026-12", "en"), "Dec 2026");
  assert.equal(periodText("month", "2026-12", "zh-CN"), "2026年12月");
  assert.equal(periodText("day", "2026-11-16", "en"), "16 Nov 2026");
  assert.equal(periodText("datetime", withTime("2026-11-16", 9, 5), "en"), "16 Nov 2026 09:05");
  assert.deepEqual(weekdayLabels("en").slice(0, 2), ["Mo", "Tu"]);
});

test("no screen uses a native date, month or date-time input", () => {
  const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
  // Pages due to be deleted (COMMERCIAL_PRODUCT_DESIGN_2) and the reports editor (its own worker)
  // are listed; the list may only shrink.
  const ALLOWED = new Set([
    "components/strategy/StrategyBacktestWorkspace.tsx",
    "components/strategy/StrategyDesignWorkspace.tsx",
    "components/strategy/SpreadLabWorkspace.tsx",
  ]);
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const full = path.join(dir, name);
      return statSync(full).isDirectory() ? files(full) : name.endsWith(".tsx") ? [full] : [];
    });
  for (const file of files(SRC)) {
    const rel = path.relative(SRC, file).split(path.sep).join("/");
    if (ALLOWED.has(rel)) continue;
    assert.doesNotMatch(readFileSync(file, "utf8"), /type="(date|month|datetime-local|time)"/, rel);
  }
});
