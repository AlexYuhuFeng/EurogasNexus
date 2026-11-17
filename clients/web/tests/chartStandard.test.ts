/**
 * The in-app chart standard (COMMERCIAL_PRODUCT_DESIGN_2 F.1/F.2), one test per rule of the
 * model: history bands that never claim more years than are held, the gas-year axis, end labels
 * that never collide, rules, ghost lines, comparisons, small multiples on one scale, stack forms,
 * the percentile strip and the waterfall's reconciliation.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  chartCsv,
  compareAt,
  endLabelRoom,
  endLabels,
  formatSigned,
  limitStack,
  percentileRank,
  placeEndLabels,
  rangePosition,
  sharedRange,
  stackForm,
  summaryFacts,
  usesEndLabels,
  valueRange,
  xLabel,
  xValues,
  type ChartData,
  type ChartSeries,
} from "../src/components/ui/charts/chartModel.ts";
import {
  BAND_YEARS,
  bandFromYears,
  bySeason,
  historyPlan,
  isCompleteSeason,
  percentileBandFromYears,
  quantile,
  seasonIndex,
  seasonKeys,
  seasonLabel,
  seasonOf,
  seasonTicks,
} from "../src/components/ui/charts/seasonModel.ts";
import { waterfallCsv, waterfallGeometry, waterfallSteps } from "../src/components/ui/charts/waterfallModel.ts";

const line = (id: string, values: (number | null)[], extra: Partial<ChartSeries> = {}): ChartSeries => ({ id, label: id.toUpperCase(), values, ...extra });

/* ---------------------------------------------------------------- history bands (F.2) */

test("history: no complete prior year means no band, and the subtitle says where history starts", () => {
  const plan = historyPlan([], "2026-03-01");
  assert.equal(plan.mode, "none");
  assert.deepEqual(plan.years, []);
  assert.equal(plan.label.key, "chart.history.from");
  assert.equal(plan.label.values.date, "2026-03-01");
});

test("history: one to four prior years are grey lines, labelled with the exact count", () => {
  const one = historyPlan(["2025/26"]);
  assert.equal(one.mode, "lines");
  assert.equal(one.label.key, "chart.history.one_year");
  const four = historyPlan(["2024/25", "2022/23", "2025/26", "2023/24"]);
  assert.equal(four.mode, "lines");
  assert.deepEqual(four.years, ["2022/23", "2023/24", "2024/25", "2025/26"]);
  assert.equal(four.label.key, "chart.history.years_held");
  assert.equal(four.label.values.count, 4);
});

test("history: five or more prior years draw the band from the last five, named by first and last", () => {
  const plan = historyPlan(["2019/20", "2020/21", "2021/22", "2022/23", "2023/24", "2024/25", "2025/26"]);
  assert.equal(plan.mode, "band");
  assert.equal(plan.years.length, BAND_YEARS);
  assert.deepEqual(plan.years, ["2021/22", "2022/23", "2023/24", "2024/25", "2025/26"]);
  assert.deepEqual(plan.label.values, { count: 5, first: "2021/22", last: "2025/26" });
});

test("history: the label never claims more years than the band is drawn from", () => {
  for (let held = 0; held <= 8; held += 1) {
    const years = Array.from({ length: held }, (_, index) => `${2015 + index}/${String((16 + index) % 100).padStart(2, "0")}`);
    const plan = historyPlan(years, "2026-01-01");
    const claimed = Number(plan.label.values.count ?? 0);
    assert.ok(claimed <= held, `held ${held}, label claims ${claimed}`);
    assert.equal(claimed, plan.years.length);
    if (plan.mode === "band") {
      const band = bandFromYears(plan.years.map(() => [1, 2, 3]));
      assert.equal(band.years, claimed);
    }
  }
});

test("band statistics: min, max and mean of the years at each day (golden, hand-computed)", () => {
  // Five years at three days. Day 0: 60, 70, 65, 72, 58 -> min 58, max 72, mean 325/5 = 65.
  // Day 1: 61, 71, 66, 73, 59 -> 59, 73, 66. Day 2: one year missing -> gap in all three.
  const years = [
    [60, 61, 62],
    [70, 71, 72],
    [65, 66, null],
    [72, 73, 74],
    [58, 59, 60],
  ];
  const band = bandFromYears(years);
  assert.deepEqual(band.low, [58, 59, null]);
  assert.deepEqual(band.high, [72, 73, null]);
  assert.deepEqual(band.mean, [65, 66, null]);
  assert.equal(band.years, 5);
});

test("percentile band: linear interpolation between ranks, with the same gap rule", () => {
  assert.equal(quantile([1, 2, 3, 4, 5], 0.1), 1.4);
  assert.equal(quantile([1, 2, 3, 4, 5], 0.9), 4.6);
  const band = percentileBandFromYears([[1, 1], [2, null], [3, 3], [4, 4], [5, 5]], 10, 90);
  assert.deepEqual(band.low, [1.4, null]);
  assert.deepEqual(band.high, [4.6, null]);
});

/* ---------------------------------------------------------------- the season axis */

test("season axis: 365 days from 1 October to 30 September, no 29 February slot", () => {
  const keys = seasonKeys();
  assert.equal(keys.length, 365);
  assert.equal(keys[0], "10-01");
  assert.equal(keys[364], "09-30");
  assert.ok(!keys.includes("02-29"));
  assert.equal(seasonKeys(1)[0], "01-01");
  assert.equal(seasonIndex("2026-10-01"), 0);
  assert.equal(seasonIndex("2026-11-17"), 47);
  assert.equal(seasonIndex("2024-02-29"), -1);
  assert.equal(seasonIndex("2027-09-30"), 364);
});

test("season axis: a day's gas year, its label, month-start ticks and the x it is drawn at", () => {
  assert.equal(seasonOf("2026-11-17"), "2026/27");
  assert.equal(seasonOf("2027-09-30"), "2026/27");
  assert.equal(seasonOf("2026-09-30"), "2025/26");
  assert.equal(seasonOf("2026-03-01", 1), "2026");
  assert.equal(seasonLabel("11-17"), "17 Nov");
  const ticks = seasonTicks(seasonKeys(), 12);
  assert.equal(ticks.length, 12);
  assert.deepEqual(ticks.slice(0, 3).map((tick) => tick.label), ["Oct", "Nov", "Dec"]);
  assert.deepEqual(seasonTicks(seasonKeys(), 6).map((tick) => tick.label), ["Oct", "Dec", "Feb", "Apr", "Jun", "Aug"]);
  assert.deepEqual(xValues({ axis: "season", x: ["10-01", "10-02"] }), [0, 1]);
  assert.equal(xLabel("season", "02-28"), "28 Feb");
});

test("season axis: days fall into their gas years; a leap day is left out, a missing day stays a gap", () => {
  const seasons = bySeason([
    { day: "2024-02-28", value: 40 },
    { day: "2024-02-29", value: 39.5 },
    { day: "2024-03-01", value: 39 },
    { day: "2024-10-01", value: 90 },
    { day: "2024-10-03", value: 91 },
  ]);
  const year = seasons.get("2023/24")!;
  assert.equal(year[seasonIndex("2024-02-28")], 40);
  assert.equal(year[seasonIndex("2024-03-01")], 39);
  assert.equal(year[seasonIndex("2024-03-01") - 1], 40, "1 March follows 28 February; 29 February has no slot");
  const next = seasons.get("2024/25")!;
  assert.equal(next[0], 90);
  assert.equal(next[1], null);
  assert.equal(next[2], 91);
});

test("a prior year counts as held only when it covers 95% of its days", () => {
  const full = new Array<number | null>(365).fill(50);
  assert.ok(isCompleteSeason(full));
  const thin = full.map((value, index) => (index < 20 ? null : value));
  assert.ok(!isCompleteSeason(thin));
});

/* ---------------------------------------------------------------- labels instead of a legend */

test("end labels: up to four lines are labelled at their ends; a fifth line brings the legend back", () => {
  const four: ChartData = { axis: "gas-day", x: ["2026-11-01", "2026-11-02"], xTitle: "", unit: "%", series: ["a", "b", "c", "d"].map((id) => line(id, [1, 2])) };
  assert.ok(usesEndLabels(four));
  const five: ChartData = { ...four, series: [...four.series, line("e", [1, 2])] };
  assert.ok(!usesEndLabels(five));
  const bars: ChartData = { ...four, series: [line("a", [1, 2], { style: "bar" })] };
  assert.ok(!usesEndLabels(bars), "bars keep their legend");
});

test("end labels: one line shows its value alone; several show name and value at the last point held", () => {
  const one: ChartData = { axis: "period", x: ["2026-12", "2027-01", "2027-02"], xTitle: "", unit: "EUR/MWh", series: [line("ttf", [30, 31.2, null], { decimals: 2 })] };
  assert.deepEqual(endLabels(one).map((label) => [label.text, label.index]), [["31.20", 1]]);
  const two: ChartData = { ...one, series: [line("ttf", [30, 31.2, 32]), line("prior", [29.5, 30.5, 31], { ghost: true, label: "Prior close" })] };
  const labels = endLabels(two);
  assert.deepEqual(labels.map((label) => label.text), ["TTF 32.00", "Prior close 31.00"]);
  assert.equal(labels[1].ghost, true);
  assert.ok(endLabelRoom(labels) >= 60);
});

test("end labels never collide: pushed apart by the gap and kept inside the plot", () => {
  const placed = placeEndLabels([{ y: 50 }, { y: 52 }, { y: 51 }, { y: 195 }], 0, 200, 14);
  const ys = placed.map((item) => item.placedY).sort((a, b) => a - b);
  for (let index = 1; index < ys.length; index += 1) assert.ok(ys[index] - ys[index - 1] >= 14 - 1e-9);
  assert.ok(ys[0] >= 4 && ys[ys.length - 1] <= 200);
  const crowded = placeEndLabels([{ y: 190 }, { y: 191 }, { y: 192 }], 0, 200, 14);
  assert.ok(Math.max(...crowded.map((item) => item.placedY)) <= 200);
});

/* ---------------------------------------------------------------- rules, ghosts, comparisons */

test("rules: the axis takes in a target and the zero line, so the rule is always drawn", () => {
  const data: ChartData = {
    axis: "period",
    x: ["2026-12", "2027-01"],
    xTitle: "",
    unit: "EUR/MWh",
    series: [line("spread", [0.4, 0.8])],
    rules: [{ id: "zero", value: 0, kind: "zero" }, { id: "cost", value: 0.97, label: "route cost 0.97", kind: "threshold" }],
  };
  const [low, high] = valueRange(data)!;
  assert.ok(low <= 0 && high >= 0.97);
  // A rule on its own is not a chart.
  assert.equal(valueRange({ ...data, series: [line("spread", [null, null])] }), null);
});

test("a ghost line (last year) is labelled and summarised like a line, but drawn as context", () => {
  const data: ChartData = { axis: "season", x: ["10-01", "10-02"], xTitle: "", unit: "%", series: [line("this", [70, 71]), line("last", [80, 79.5], { ghost: true, label: "Last year" })] };
  const facts = summaryFacts(data);
  assert.equal(facts.length, 2);
  assert.equal(facts[1].ghost, true);
  assert.equal(facts[1].last, "79.50");
  assert.equal(facts[0].lastAt, "2 Oct");
});

test("the readout's comparison: a series against the band's mean, with a true minus", () => {
  const data: ChartData = {
    axis: "season",
    x: ["10-01", "10-02"],
    xTitle: "",
    unit: "%",
    series: [line("this", [70, 64.8])],
    bands: [{ id: "range", label: "5-yr range", years: ["a", "b", "c", "d", "e"], low: [60, 60], high: [80, 80], mean: [71, 71] }],
  };
  const difference = compareAt(data, { series: "this", against: "range", label: "vs 5-yr mean" }, 1)!;
  assert.equal(Number(difference.toFixed(1)), -6.2);
  assert.equal(formatSigned(difference, 1), "−6.2");
  assert.equal(formatSigned(0.04, 1), "0.0");
  assert.equal(formatSigned(2, 1), "+2.0");
});

test("the CSV carries the band's low, high and mean beside the series; a gap is an empty cell", () => {
  const data: ChartData = {
    axis: "season",
    x: ["10-01", "10-02"],
    xTitle: "Day of gas year",
    unit: "%",
    series: [line("this", [70, null], { simulated: true, label: "This year" })],
    bands: [{ id: "range", label: "5-yr range 2021/22–2025/26", meanLabel: "5-yr mean", years: ["a", "b", "c", "d", "e"], low: [60, null], high: [80, null], mean: [71, null] }],
  };
  assert.equal(
    chartCsv(data),
    "Day of gas year,This year [simulated] (%),5-yr range 2021/22–2025/26 low (%),5-yr range 2021/22–2025/26 high (%),5-yr mean (%)\n" +
      "10-01,70,60,80,71\n10-02,,,,\n",
  );
});

/* ---------------------------------------------------------------- small multiples, stacks */

test("small multiples share one y range by default, so the panels compare", () => {
  const panel = (values: number[]): ChartData => ({ axis: "season", x: values.map((_, index) => String(index)), xTitle: "", unit: "%", series: [line("fill", values)] });
  const range = sharedRange([panel([40, 50]), panel([70, 90]), panel([])])!;
  assert.ok(range[0] <= 40 && range[1] >= 90);
});

test("stacks: an area beyond 14 points, bars up to 14", () => {
  assert.equal(stackForm(14), "bar");
  assert.equal(stackForm(15), "area");
});

test("stacks: at most four members by size, the rest summed as one grey Other", () => {
  const members = [
    line("a", [10, 10]),
    line("b", [1, 1]),
    line("c", [5, 5]),
    line("d", [3, null]),
    line("e", [2, 2]),
    line("f", [null, 4]),
  ];
  const limited = limitStack(members, "Other");
  assert.deepEqual(limited.map((item) => item.id), ["a", "c", "e", "f", "other"]);
  const other = limited.at(-1)!;
  assert.deepEqual(other.values, [4, 1]);
  assert.equal(other.colour, 8);
  assert.equal(limitStack(members.slice(0, 5), "Other").length, 5, "five members stay as they are");
});

/* ---------------------------------------------------------------- percentile strip */

test("percentile strip: the place in the range, clamped and said when outside", () => {
  assert.deepEqual(rangePosition(70, 60, 80), { position: 50, outside: null });
  assert.deepEqual(rangePosition(55, 60, 80), { position: 0, outside: "below" });
  assert.deepEqual(rangePosition(85, 60, 80), { position: 100, outside: "above" });
  assert.equal(percentileRank(3, [1, 2, 3, 4]), 62.5);
  assert.equal(percentileRank(3, []), null);
});

/* ---------------------------------------------------------------- waterfall */

test("waterfall: FOB to delivered cost in floating steps; the stated total reconciles", () => {
  // C.3 worked example, per MMBtu delivered: FOB 6.525, boil-off 0.079, freight 0.437 -> 7.041.
  const model = waterfallSteps([
    { id: "fob", label: "FOB", value: 6.525, kind: "total" },
    { id: "boil", label: "Boil-off", value: 0.079 },
    { id: "freight", label: "Freight", value: 0.437 },
    { id: "des", label: "DES-equivalent", value: 7.041, kind: "total" },
  ]);
  assert.ok(model.reconciles, `difference ${model.difference}`);
  assert.deepEqual(model.steps.map((step) => [step.from, Number(step.to.toFixed(3))]), [[0, 6.525], [6.525, 6.604], [6.604, 7.041], [0, 7.041]]);
  const csv = waterfallCsv(model, "USD/MMBtu", { step: "Step", change: "Change", total: "Running total" });
  assert.match(csv, /^Step,Change \(USD\/MMBtu\),Running total \(USD\/MMBtu\)\nFOB,,6.525\nBoil-off,0.079,6.604\n/);
});

test("waterfall: a total that is not the sum of its steps is reported, not drawn as if it were", () => {
  const model = waterfallSteps([
    { id: "start", label: "Start", value: 10, kind: "total" },
    { id: "up", label: "Up", value: 2 },
    { id: "end", label: "End", value: 13, kind: "total" },
  ]);
  assert.equal(model.reconciles, false);
  assert.equal(model.difference, 1);
});

test("waterfall geometry: vertical bars grow upward from the zero line; horizontal ones rightward", () => {
  const model = waterfallSteps([
    { id: "a", label: "A", value: 10, kind: "total" },
    { id: "b", label: "B", value: -4 },
  ]);
  const vertical = waterfallGeometry(model, 200, 100, true);
  assert.equal(vertical[0].start, 100);
  assert.equal(vertical[0].end, 0);
  assert.equal(vertical[1].sign, "down");
  const horizontal = waterfallGeometry(model, 100, 200, false);
  assert.equal(horizontal[0].start, 0);
  assert.equal(horizontal[0].end, 200);
  assert.equal(horizontal[1].end, 120);
});
