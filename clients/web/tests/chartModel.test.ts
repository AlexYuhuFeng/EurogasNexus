/** The chart layer's pure rules (UX-09): gas-day ticks, periods, stacks, gaps and the CSV export. */
import assert from "node:assert/strict";
import test from "node:test";

import {
  chartCsv,
  gasDayTicks,
  nextPointIndex,
  periodLabel,
  periodTicks,
  splitForecast,
  stackBases,
  valueRange,
  xLabel,
  xValues,
  type ChartData,
} from "../src/components/ui/charts/chartModel.ts";

function days(first: string, count: number): string[] {
  const start = Date.parse(`${first}T00:00:00Z`);
  return Array.from({ length: count }, (_, index) => new Date(start + index * 86_400_000).toISOString().slice(0, 10));
}

test("a gas-day series is plotted at gas-day starts (05:00 UTC winter, 04:00 UTC summer), never midnight", () => {
  const [winter, summer] = xValues({ axis: "gas-day", x: ["2026-11-16", "2026-07-01"] });
  assert.equal(new Date(winter * 1000).toISOString(), "2026-11-16T05:00:00.000Z");
  assert.equal(new Date(summer * 1000).toISOString(), "2026-07-01T04:00:00.000Z");
  // Across the October clock change the step is 25 hours, as the gas day is.
  const [before, after] = xValues({ axis: "gas-day", x: ["2026-10-24", "2026-10-25"] });
  assert.equal(after - before, 25 * 3600);
  assert.equal(xLabel("gas-day", "2026-11-16"), "16 Nov 2026");
});

test("gas-day ticks fit the budget, keep the last day, and fall back to month starts", () => {
  const week = days("2026-11-10", 7);
  assert.deepEqual(gasDayTicks(week, 10), [0, 1, 2, 3, 4, 5, 6]);
  const month = days("2026-10-18", 30);
  const ticks = gasDayTicks(month, 6);
  assert.ok(ticks.length <= 6, String(ticks));
  assert.equal(ticks.at(-1), 29, "today keeps its tick");
  const season = days("2026-07-20", 120);
  const monthly = gasDayTicks(season, 6);
  assert.ok(monthly.every((index) => season[index].endsWith("-01")), monthly.map((i) => season[i]).join());
  assert.equal(gasDayTicks([], 5).length, 0);
});

test("delivery periods read as the desk names them, ticks thinned evenly", () => {
  assert.equal(periodLabel("2026-12"), "Dec-26");
  assert.equal(periodLabel("Q1-27"), "Q1-27");
  assert.deepEqual(xValues({ axis: "period", x: ["2026-12", "2027-01"] }), [0, 1]);
  assert.deepEqual(periodTicks(36, 12), [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33]);
  assert.deepEqual(periodTicks(5, 12), [0, 1, 2, 3, 4]);
});

test("stacks go up for supply and down for an injection; a gap stays a gap", () => {
  const series = [
    { id: "a", label: "Norway", values: [10, 10, null], stack: true },
    { id: "b", label: "LNG", values: [5, 4, 3], stack: true },
    { id: "c", label: "Storage", values: [2, -3, 1], stack: true },
  ];
  const bases = stackBases(series, 3);
  assert.deepEqual(bases.get("a"), [0, 0, null]);
  assert.deepEqual(bases.get("b"), [10, 10, 0]);
  assert.deepEqual(bases.get("c"), [15, 0, 3]);
  const range = valueRange({ axis: "gas-day", x: ["1", "2", "3"], xTitle: "Gas day", unit: "GWh/d", series })!;
  assert.ok(range[0] <= -3 && range[1] >= 17, String(range));
});

test("the CSV export is the plotted data: units in the header, gaps empty, simulated named", () => {
  const data: ChartData = {
    axis: "period",
    x: ["2026-12", "2027-01"],
    xTitle: "Delivery month",
    unit: "EUR/MWh",
    series: [
      { id: "ttf", label: "TTF", values: [31.4, null], simulated: true },
      { id: "the", label: "THE, Germany", values: [32.1, 33] },
    ],
  };
  assert.equal(chartCsv(data), 'Delivery month,TTF [simulated] (EUR/MWh),"THE, Germany (EUR/MWh)"\n2026-12,31.4,32.1\n2027-01,,33\n');
});

test("keyboard steps skip points no series has; a forecast shares its joining point", () => {
  const data: ChartData = {
    axis: "gas-day",
    x: days("2026-11-01", 5),
    xTitle: "Gas day",
    unit: "%",
    series: [{ id: "f", label: "Fill", values: [1, null, null, 4, 5] }],
  };
  assert.equal(nextPointIndex(data, 0, 1), 3);
  assert.equal(nextPointIndex(data, 3, -1), 0);
  assert.equal(nextPointIndex(data, 4, 1), 4);
  const [measured, forecast] = splitForecast({ id: "c", label: "Call", values: [1, 2, 3, 4], forecastFrom: 2 });
  assert.deepEqual(measured.values, [1, 2, null, null]);
  assert.deepEqual(forecast!.values, [null, 2, 3, 4]);
});
