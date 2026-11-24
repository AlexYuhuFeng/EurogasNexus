import assert from "node:assert/strict";
import test from "node:test";

import type { DailyBalanceDTO, GasDayCutoffDTO } from "../src/api/client.ts";
import { cutoffUrgency, dailyBalanceRateText, formatQuantity, mwText, nextCutoff, timeLeft } from "../src/app/model/gasDayModel.ts";

const cut = (key: GasDayCutoffDTO["key"], at: string): GasDayCutoffDTO => ({
  key, name: null, at_utc: at, basis: "assumption", source: "default", passed: false,
});

test("the next cut-off is the first one still ahead; none after the gas day ends", () => {
  const cuts = [
    cut("nomination", "2026-11-18T13:00:00+00:00"),
    cut("last_renomination", "2026-11-20T02:00:00+00:00"),
    cut("gas_day_end", "2026-11-20T05:00:00+00:00"),
  ];
  const now = Date.parse("2026-11-19T09:15:00Z");
  assert.equal(nextCutoff(cuts, now)?.key, "last_renomination");
  assert.deepEqual(timeLeft(cuts[1].at_utc, now), { hours: 16, minutes: 45 });
  assert.equal(nextCutoff(cuts, Date.parse("2026-11-20T03:00:00Z"))?.key, "gas_day_end");
  assert.equal(nextCutoff(cuts, Date.parse("2026-11-20T06:00:00Z")), null);
  assert.deepEqual(timeLeft(cuts[0].at_utc, now), { hours: 0, minutes: 0 });
});

test("quantities read in desk format, signed for the net, MW beside a continental figure", () => {
  assert.equal(formatQuantity({ value: 781264, unit: "th/d", mwh: 22896.6 }, true), "+781,264");
  assert.equal(formatQuantity({ value: -503.3, unit: "MWh/d", mwh: -503.3, mw: -21 }, true), "−503");
  assert.equal(formatQuantity({ value: 0.2, unit: "MWh/d", mwh: 0.2 }, true), "0");
  assert.equal(mwText({ value: -503.3, unit: "MWh/d", mwh: -503.3, mw: -21 }, true), "−21");
  assert.equal(mwText({ value: 781264, unit: "th/d", mwh: 22896.6 }), null);
});

test("time left turns amber within two hours and red within thirty minutes", () => {
  const at = "2026-11-19T13:00:00Z";
  assert.equal(cutoffUrgency(at, Date.parse("2026-11-19T09:00:00Z")), "open");
  assert.equal(cutoffUrgency(at, Date.parse("2026-11-19T11:30:00Z")), "soon");
  assert.equal(cutoffUrgency(at, Date.parse("2026-11-19T12:45:00Z")), "imminent");
  assert.equal(cutoffUrgency(at, Date.parse("2026-11-19T13:05:00Z")), "none");
});

test("the daily balance names its cash-out rate from the response, never a client default", () => {
  const t = (key: string, options?: Record<string, unknown>) => `${key}${options ? JSON.stringify(options) : ""}`;
  const day = (cash_out: DailyBalanceDTO["days"][number]["cash_out"]) => ({
    gas_day: "2026-11-24", supply: 0, exchange_bought: 0, exchange_sold: 0, bilateral_bought: 0, bilateral_sold: 0,
    residual_mwh: 100, state: "long" as const, cash_out_cost: cash_out?.value ?? null, cash_out,
  });
  const balance = (...days: ReturnType<typeof day>[]): DailyBalanceDTO => ({ hub: "NBP", currency: "GBP", delivery_ratio: 1, contracts: [], days });
  const approved = balance(day({
    value: 120, currency: "GBP", basis: "assumption", rate: 1.2, rate_unit: "GBP/MWh", side: "long_discount",
    assumption_set: "Demo demo-uk-nbp balancing", assumption_version: 1,
  }));
  const text = dailyBalanceRateText(approved, t) ?? "";
  assert.ok(text.startsWith("balance.rate_source"));
  assert.ok(text.includes("\"rate\":1.2") && text.includes("Demo demo-uk-nbp balancing") && text.includes("\"version\":1"));
  const missing = balance(day({ value: null, currency: "GBP", basis: "missing", reason: "none" }));
  assert.equal(dailyBalanceRateText(missing, t), "balance.rate_missing");
  assert.equal(dailyBalanceRateText(balance(), t), null);
});
