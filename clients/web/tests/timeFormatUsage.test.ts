import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// One way to show an instant or a number (UX_REFERENCE rule 17): app/time/timeFormat.ts, the
// Instant primitive, useInstantFormatter / displayTime. Hand-written UTC strings and browser-locale
// formatting are counted per file; a file may only go down from the recorded count, and a new file
// starts at zero. `node --test tests/timeFormatUsage.test.ts` with UPDATE_TIME_BASELINE=1 lowers the
// baseline after a conversion.
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src");
const BASELINE = path.join(ROOT, "tests", "fixtures", "timeFormatBaseline.json");

const PATTERNS: Record<string, RegExp> = {
  // A date drawn by hand or in the browser's locale.
  // (A date key, toISOString().slice(0, 10), is arithmetic, not display, and is not counted.)
  adhocTime: /toISOString\(\)\.slice\((?:0, (?:1[3-9])|1[1-9])|toLocaleDateString\(|toLocaleTimeString\(|\bUTC`|\} UTC</g,
  // A number in the browser's locale rather than the app's language.
  browserLocaleNumber: /\.toLocaleString\(\s*\)|\.toLocaleString\(undefined|\.toLocaleString\(\[\]/g,
};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "time" ? [] : sources(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

function measure(): Record<string, Record<string, number>> {
  const counts: Record<string, Record<string, number>> = {};
  for (const file of sources(SRC)) {
    const text = readFileSync(file, "utf8");
    const rel = path.relative(ROOT, file).split(path.sep).join("/");
    for (const [name, pattern] of Object.entries(PATTERNS)) {
      const found = text.match(pattern)?.length ?? 0;
      if (found) (counts[rel] ??= {})[name] = found;
    }
  }
  return counts;
}

test("no new hand-written time or browser-locale number; counts only go down", () => {
  const measured = measure();
  if (process.env.UPDATE_TIME_BASELINE === "1") {
    writeFileSync(BASELINE, `${JSON.stringify(measured, null, 2)}\n`);
  }
  const baseline = JSON.parse(readFileSync(BASELINE, "utf8")) as Record<string, Record<string, number>>;
  for (const [file, kinds] of Object.entries(measured)) {
    for (const [kind, count] of Object.entries(kinds)) {
      const allowed = baseline[file]?.[kind] ?? 0;
      assert.ok(count <= allowed, `${file}: ${count} ${kind} (allowed ${allowed}); use app/time/timeFormat.ts`);
    }
  }
});

test("the shell's own surfaces use the formatter only", () => {
  const measured = measure();
  for (const file of [
    "src/components/TopBarStatus.tsx",
    "src/components/ProjectionContextStrip.tsx",
    "src/components/AlertCenter.tsx",
    "src/components/MarketTerminal.tsx",
    "src/components/decision/DayBoardPanel.tsx",
  ]) {
    assert.equal(measured[file]?.adhocTime ?? 0, 0, file);
  }
});
