/** Forward balance (CP-25): the headline sentence, the charts and the rows the page shows. */
import assert from "node:assert/strict";
import test from "node:test";

import type { ForwardBalanceDTO } from "../src/api/client.ts";
import { balanceChart, bandPosition, forwardRows, headlinePhrase, monthEnd, storageChart } from "../src/app/model/forwardBalanceModel.ts";

const t = (key: string) => key;

function day(dayKey: string, extra: Partial<ForwardBalanceDTO["daily"][number]> = {}): ForwardBalanceDTO["daily"][number] {
  return {
    day: dayKey, horizon_days: 1, demand_gwh_d: 9000, demand_error_gwh_d: 170, demand_normal_gwh_d: 8800, hdd_normal: 11, hdd_change: 0,
    norway_gwh_d: 4400, norway_normal_gwh_d: 4450, norway_outage_gwh_d: 0, lng_gwh_d: 2800, lng_normal_gwh_d: 2500,
    storage_gwh_d: 1800, storage_normal_gwh_d: 1850, gap_gwh_d: -1800, inventory_twh: 380, fill_pct: 71.2,
    band_low_pct: 71.4, band_high_pct: 73.7, band_mean_pct: 72, methods: {}, flags: [], ...extra,
  };
}

const dto = {
  hub: "nwe", unit: "GWh/d", as_of: "2026-11-18", simulated: false,
  headline: { direction: "tighter", gwh_d: 650, signed_gwh_d: 650, window: { from: "2026-11-19", to: "2026-12-02", days: 14 }, main_driver: "norway", contributions_gwh_d: { demand: 50, norway: 600, lng: 0 }, norway_outage_gwh_d: 600 },
  daily: [day("2026-11-19"), day("2026-11-20", { fill_pct: 74 })],
  monthly: [{ month: "2026-12", days: 31, demand_gwh_d: 9500, demand_error_gwh_d: 960, hdd_normal: 12, hdd_normal_std: 1.5, hdd_years: 30, hdd_change: 0, norway_gwh_d: 4400, norway_outage_gwh_d: 100, lng_gwh_d: 2800, storage_gwh_d: 2300, gap_gwh_d: -2300, inventory_twh_end: 300, fill_pct_end: 53.5, band_low_pct: 49, band_high_pct: 53, band_mean_pct: 51, methods: {} }],
  lines: [], demand_model: null,
  backtest: { daily: { origins: 0, from: null, to: "2026-11-18", horizons: [], method: "" }, monthly: { n: 0, mae_gwh_d: null, method: "", months: [] } },
  storage: { fill_pct: 71.6, as_of: "2026-11-18", band_label: "5-yr range 2021/22–2025/26", target: { pct: 90, deadline: "2026-12-01", implied_fill_pct: 66, within_horizon: true, gap_pts: -24 } },
  overridden: [], what_if: { temperature_shift_c: 0, norway_gwh_d: null, lng_gwh_d: null, added_outage: null }, outages_applied: 1,
  forward_curve: { hub: "TTF", for_reference_only: true, months: [] },
  weather_reference: { attribution: "Eurostat", licence: "CC BY 4.0", months: { from: "1996-01", to: "2025-12" } },
  zone_note: "", not_a_price_forecast: "",
} as ForwardBalanceDTO;

test("the headline names the direction, the size and the main reason", () => {
  const phrase = headlinePhrase(dto);
  assert.equal(phrase?.key, "fb.headline.tighter");
  assert.equal(phrase?.values.gwh, "650");
  assert.equal(phrase?.values.driver, "fb.driver.norway_below_outage");
  assert.equal(phrase?.values.outage, "600");
  assert.equal(headlinePhrase({ ...dto, headline: null }), null);
  const looser = headlinePhrase({ ...dto, headline: { ...dto.headline!, direction: "looser", main_driver: "lng", contributions_gwh_d: { demand: 0, norway: 0, lng: -400 } } });
  assert.equal(looser?.values.driver, "fb.driver.lng_above");
});

test("the balance chart stacks supply under demand and draws the normal in grey", () => {
  const chart = balanceChart(dto, t);
  assert.deepEqual(chart.series.map((s) => s.id), ["norway", "lng", "storage", "demand", "demand_normal"]);
  assert.ok(chart.series.slice(0, 3).every((s) => s.stack));
  assert.ok(chart.series[4].ghost);
});

test("the storage path runs from the first to the last day, then each month's end, against band and target", () => {
  const chart = storageChart(dto, t)!;
  assert.deepEqual(chart.x, ["2026-11-19", "2026-11-20", "2026-12-31"]);
  assert.deepEqual(chart.series[0].values, [71.2, 74, 53.5]);
  assert.equal(chart.bands?.[0].label, "5-yr range 2021/22–2025/26");
  assert.equal(chart.rules?.[0].value, 90);
  assert.equal(monthEnd("2027-02"), "2027-02-28");
});

test("rows: days then months, and where the fill sits against its band", () => {
  const rows = forwardRows(dto);
  assert.deepEqual(rows.map((r) => r.kind), ["day", "day", "month"]);
  assert.equal(rows[2].fill, 53.5);
  assert.equal(bandPosition(rows[0].fill, rows[0].bandLow, rows[0].bandHigh), "below");
  assert.equal(bandPosition(rows[1].fill, rows[1].bandLow, rows[1].bandHigh), "above");
  assert.equal(bandPosition(72, 71, 73), "within");
  assert.equal(bandPosition(null, 1, 2), null);
});
