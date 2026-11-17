/**
 * The sparkline answers "what is this value and when": points by time, gaps never
 * interpolated, the pointer snapping to a data point, the keys stepping through points, and an
 * accessible name stating first, last, low, high and how many points.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  nearestPoint,
  sparkGeometry,
  sparkPath,
  sparkSummary,
  sparkValue,
  sparkWhen,
  stepPoint,
} from "../src/components/ui/charts/sparklineModel.ts";

const days = ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"];

test("a null value and a missing gas day are gaps, never a line across", () => {
  const withNull = sparkGeometry([70, 71, null, 72, 73, 72.6], days, { width: 100, height: 20 });
  assert.equal(withNull.points.length, 5);
  assert.deepEqual(withNull.segments.map((segment) => segment.map((point) => point.index)), [[0, 1], [3, 4, 5]]);
  assert.equal((sparkPath(withNull.segments).match(/M/g) ?? []).length, 2);

  const skipped = ["2026-11-10", "2026-11-11", "2026-11-14", "2026-11-15"];
  const missing = sparkGeometry([1, 2, 3, 4], skipped, { width: 100, height: 20 });
  assert.deepEqual(missing.segments.map((segment) => segment.map((point) => point.index)), [[0, 1], [2, 3]]);
  // x follows time: the gap is as wide as the missing days.
  assert.ok(missing.points[2].x - missing.points[1].x > 2 * (missing.points[1].x - missing.points[0].x));
});

test("the lowest, highest and last points are known; the pointer snaps to a data point", () => {
  const geometry = sparkGeometry([70, 69.5, null, 74, 73, 72.6], days, { width: 100, height: 20, pad: 0 });
  assert.equal(geometry.points[geometry.min].value, 69.5);
  assert.equal(geometry.points[geometry.max].value, 74);
  assert.equal(geometry.points[geometry.last].value, 72.6);
  // A pointer over the gap snaps to the nearest point with a value.
  const gapX = 40;
  const snapped = geometry.points[nearestPoint(geometry.points, gapX)];
  assert.ok(snapped.index === 1 || snapped.index === 3, `snapped to ${snapped.index}`);
  assert.equal(nearestPoint(geometry.points, -50), 0);
  assert.equal(nearestPoint(geometry.points, 500), geometry.points.length - 1);
  assert.equal(nearestPoint([], 10), -1);
});

test("the keys step through the points, starting at the last one", () => {
  assert.equal(stepPoint(5, -1, "ArrowLeft"), 4);
  assert.equal(stepPoint(5, 4, "ArrowLeft"), 3);
  assert.equal(stepPoint(5, 0, "ArrowLeft"), 0);
  assert.equal(stepPoint(5, 3, "ArrowRight"), 4);
  assert.equal(stepPoint(5, 4, "ArrowRight"), 4);
  assert.equal(stepPoint(5, 2, "Home"), 0);
  assert.equal(stepPoint(5, 2, "End"), 4);
  assert.equal(stepPoint(5, 2, "a"), null);
  assert.equal(stepPoint(0, -1, "ArrowLeft"), null);
});

test("the readout and the accessible name use the series' unit and the gas day", () => {
  const geometry = sparkGeometry([7856, 8100, 9274], ["2026-11-02", "2026-11-03", "2026-11-04"], { width: 100, height: 20 });
  const summary = sparkSummary(geometry, "gas-day", "GWh/d", 0);
  assert.deepEqual(summary, {
    first: "7,856 GWh/d",
    firstWhen: "2 Nov 2026",
    last: "9,274 GWh/d",
    lastWhen: "4 Nov 2026",
    min: "7,856 GWh/d",
    max: "9,274 GWh/d",
    count: 3,
  });
  assert.equal(sparkValue(72.6, "%", 1), "72.6 %");
  assert.equal(sparkWhen("time", "2026-11-16T09:30:00Z"), "16 Nov 2026 09:30 UTC");
  assert.equal(sparkSummary(sparkGeometry([null, null], days, { width: 10, height: 10 }), "gas-day", "%", 1), null);
});

test("the sparkline is an inline SVG with a readout, keys and a polite live region; no chart library", () => {
  const source = readFileSync(new URL("../src/components/ui/charts/Chart.tsx", import.meta.url), "utf8");
  const sparkline = source.slice(source.indexOf("export function Sparkline("));
  assert.doesNotMatch(sparkline, /useUplot|new UPlot/);
  assert.match(sparkline, /tabIndex=\{0\}/);
  assert.match(sparkline, /onKeyDown=\{onKeyDown\}/);
  assert.match(sparkline, /aria-live="polite"/);
  assert.match(sparkline, /className="ds-sparkline-last"/);
  assert.match(sparkline, /ds-sparkline-extreme/);
  assert.match(sparkline, /onPointerMove=/);
  // Simulated stays marked in the readout.
  assert.match(sparkline, /today\.simulated_short/);
  // Every use passes its unit, a translator and where its full chart is.
  for (const file of ["components/TodayScreen.tsx", "components/MarketTerminal.tsx"]) {
    const use = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
    for (const block of use.split("<Sparkline").slice(1)) {
      const props = block.slice(0, block.indexOf("/>"));
      assert.match(props, /unit=/, file);
      assert.match(props, /t=\{t\}/, file);
      assert.match(props, /onOpen=/, file);
    }
  }
});
