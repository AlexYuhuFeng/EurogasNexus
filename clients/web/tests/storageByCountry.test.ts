/**
 * Storage by country (CP-04): the seasonal chart is drawn from the server's history exactly as
 * labelled (band years = label years, held years as grey lines, last year as a ghost, the EU
 * target as a rule), and the row headline states N in "vs N-yr".
 */
import assert from "node:assert/strict";
import test from "node:test";

import type { StorageEntityDTO } from "../src/api/client.ts";
import { headline, seasonChart, seasonCodes, sparkOf, versusAverage } from "../src/app/model/storageByCountry.ts";

const axis = Array.from({ length: 365 }, (_, index) => `k${index}`);
const fill = (value: number) => axis.map(() => value);

function entity(overrides: Partial<StorageEntityDTO> = {}): StorageEntityDTO {
  return {
    code: "DE",
    name: "Germany",
    simulated: false,
    sources: ["GIE"],
    as_of: "2026-11-16",
    received_at_utc: null,
    fill_pct: 57.19,
    stock_twh: 141.4678,
    working_capacity_twh: 247.36,
    day_change_pts: -0.31,
    day_change_twh: -0.77,
    week_change_pts: -2.1,
    week_change_twh: -5.2,
    injection_twh_d: 0.01,
    withdrawal_twh_d: 0.8,
    net_withdrawal_7d_twh_d: 0.74,
    vs_last_year: { day: "2025-11-16", fill_pct: 75.0, diff_pts: -17.81 },
    history: { mode: "band", years: ["2021/22", "2022/23", "2023/24", "2024/25", "2025/26"], label: "5-yr range 2021/22–2025/26", history_from: "2021-10-01" },
    vs_average: { years: 5, label: "5-yr avg", mean_pct: 88.0, low_pct: 69.96, high_pct: 100.26, diff_pts: -30.81, range_position: 0, outside: "below" },
    target: { pct: 90, window_open: "10-01", deadline: "12-01", gap_pts: -32.81, days_to_target_at_7d_rate: null },
    spark: [{ day: "2026-11-15", fill_pct: 57.5 }, { day: "2026-11-16", fill_pct: 57.19 }],
    season: {
      axis,
      gas_year: "2026/27",
      this_year: fill(57),
      last_year: { gas_year: "2025/26", values: fill(75) },
      lines: [],
      band: { years: ["2021/22", "2022/23", "2023/24", "2024/25", "2025/26"], label: "5-yr range 2021/22–2025/26", low: fill(70), high: fill(100), mean: fill(88) },
    },
    ...overrides,
  };
}

const labels = {
  lastYear: (year: string) => `Last year ${year}`,
  thisYear: (year: string) => year,
  mean: (count: number) => `${count}-yr mean`,
  target: (pct: number) => `EU target ${pct} %`,
  xTitle: "Day of gas year",
};

test("the seasonal chart: this year in the accent, last year a ghost, the band as labelled", () => {
  const chart = seasonChart(entity(), labels, "vs 5-yr mean")!;
  const ids = chart.data.series.map((item) => item.id);
  assert.deepEqual(ids, ["last", "this"]);
  assert.equal(chart.data.series[0].ghost, true);
  assert.equal(chart.data.series[0].label, "Last year 2025/26");
  assert.equal(chart.data.series[1].colour, 1);
  const band = chart.data.bands![0];
  assert.equal(band.label, "5-yr range 2021/22–2025/26");
  assert.equal(band.years.length, 5, "the band is drawn from exactly the years its label names");
  assert.equal(band.meanLabel, "5-yr mean");
  assert.deepEqual(chart.data.rules, [{ id: "target", value: 90, label: "EU target 90 %", kind: "target" }]);
  assert.equal(chart.subtitle, "5-yr range 2021/22–2025/26");
  assert.deepEqual(chart.compare, { series: "this", against: "range", label: "vs 5-yr mean" });
});

test("with fewer than five years the held years are grey lines and there is no band", () => {
  const short = entity({
    history: { mode: "lines", years: ["2023/24", "2024/25", "2025/26"], label: "3 prior years held", history_from: "2023-10-01" },
    season: { ...entity().season!, band: null, lines: [{ gas_year: "2023/24", values: fill(60) }, { gas_year: "2024/25", values: fill(65) }] },
    target: null,
    simulated: true,
  });
  const chart = seasonChart(short, labels, "vs last year")!;
  assert.deepEqual(chart.data.series.map((item) => [item.id, Boolean(item.ghost)]), [["y-2023/24", true], ["y-2024/25", true], ["last", true], ["this", false]]);
  assert.deepEqual(chart.data.bands, []);
  assert.deepEqual(chart.data.rules, [], "no EU target outside the EU");
  assert.ok(chart.data.series.every((item) => item.simulated), "a simulated entity is simulated in every line");
  assert.equal(chart.subtitle, "3 prior years held");
  assert.equal(chart.compare?.against, "last");
});

test("an entity without its season (not asked for) has no chart", () => {
  assert.equal(seasonChart(entity({ season: undefined }), labels, ""), null);
});

test("the headline states the fill, the N-yr comparison with N, and the day change", () => {
  const words = (count: number) => `vs ${count}-yr`;
  assert.equal(headline(entity(), words, "/d"), "57.2 % · −30.8 vs 5-yr · −0.31/d");
  assert.equal(versusAverage(entity({ vs_average: { ...entity().vs_average, years: 0, diff_pts: null } }), words), null);
  assert.deepEqual(sparkOf(entity()).days, ["2026-11-15", "2026-11-16"]);
  assert.deepEqual(seasonCodes("EU", "DE"), ["EU", "DE"]);
  assert.deepEqual(seasonCodes("EU", null), ["EU"]);
});
