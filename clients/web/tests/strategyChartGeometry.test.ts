import assert from "node:assert/strict";
import test from "node:test";
import { chartAreaPath, chartLinePath, isChartValue } from "../src/components/strategy/strategyChartGeometry.ts";

const x = (index: number) => index * 10;
const y = (value: number) => 100 - value;

test("missing and non-finite observations break the line without shifting later dates", () => {
  const points = [10, null, 20, 30, undefined, Number.NaN, Infinity, 0].map((value, i) => ({ label: String(i), value }));
  assert.equal(chartLinePath(points, x, y), "M0.0,90.0 M20.0,80.0 L30.0,70.0 M70.0,100.0");
});

test("zero drawdown remains real; entirely unavailable data has no line", () => {
  assert.equal(isChartValue(0), true);
  assert.equal(chartLinePath([{label: "day", value: 0}], x, y), "M0.0,100.0");
  assert.equal(chartLinePath([{label: "day", value: null}], x, y), "");
});


test("area closes at the zero line for zero, positive and negative PnL", () => {
  for (const value of [0, 10, -10]) {
    const points = [{ label: "a", value }, { label: "b", value }];
    assert.equal(chartAreaPath(points, x, y), `M0.0,${y(value).toFixed(1)} L10.0,${y(value).toFixed(1)} L10.0,100.0 L0.0,100.0 Z`);
  }
  assert.equal(chartAreaPath([{label: "a", value: 1}, {label: "b", value: null}], x, y), "");
});
