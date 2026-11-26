import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// One fold primitive (review 2026-11-26): the pages this review touched fold through
// components/ui/Fold.tsx, not a <details> with its own styling.
const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the folds on Position, its warnings and Reports are the shared Fold", () => {
  for (const file of ["../src/components/CommercialWarningList.tsx", "../src/components/PortfolioWorkspace.tsx", "../src/components/PositionLadderPanel.tsx", "../src/components/ReportsWorkspace.tsx"]) {
    const source = read(file);
    assert.match(source, /<Fold\b/, file);
  }
  for (const css of ["../src/components/commercial-workflow.css", "../src/styles/reports.css"]) {
    assert.doesNotMatch(read(css), /-fold\b[^{]*>\s*summary|diagnostic-detail/, css);
  }
  const fold = read("../src/components/ui/Fold.tsx");
  // A toggle caused by `open` is not reported as the reader's.
  assert.match(fold, /if \(onToggle && now !== open\) onToggle\(now\)/);
});
