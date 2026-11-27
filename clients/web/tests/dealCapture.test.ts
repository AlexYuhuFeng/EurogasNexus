import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { dealSourceText, differenceText, shownDecimal, todayIso, unacknowledged } from "../src/app/model/dealCaptureModel.ts";
import { PRODUCT_MODES } from "../src/app/navigation/modeNavigation.ts";

const t = (key: string, options?: Record<string, unknown>) => `${key}${options ? JSON.stringify(options) : ""}`;

test("the blotter is a task of the book, not a page of its own", () => {
  const book = PRODUCT_MODES.find((mode) => mode.id === "book");
  const blotter = book?.tasks.find((task) => task.id === "blotter");
  assert.equal(blotter?.page, "contracts");
  assert.equal(blotter?.pageTask, "deals");
  assert.deepEqual(blotter?.permissions, ["portfolio.read"]);
});

test("each row says where the deal came from: file and line, or by hand and by whom", () => {
  assert.equal(dealSourceText({ source: { kind: "file", file_name: "ice.csv", line: 4 } }, t), 'deals.source_file{"file":"ice.csv","line":4}');
  assert.equal(dealSourceText({ source: { kind: "manual", entered_by: "trader.a" } }, t), 'deals.source_manual{"who":"trader.a"}');
});

test("exact decimals are formatted for display only, in the app's language", () => {
  assert.equal(shownDecimal("-1860", "en", 0), "−1,860");
  assert.equal(shownDecimal(null, "en", 0), "–");
  assert.equal(shownDecimal("31.25", "zh-CN", 3), "31.250");
  assert.equal(todayIso(new Date("2026-11-27T23:30:00Z")), "2026-11-27");
});

test("every difference reads both sides, and the close waits for a note on each", () => {
  const volume = { id: "a", kind: "volume", deal_key: "ICE:1", etrm_trade_id: "E1", hub: "TTF", product: "Dec-26", matched_by: "terms" as const, captured: null, etrm: null, detail: { captured_mwh: "7440", etrm_mwh: "7750" } };
  const missing = { ...volume, id: "b", kind: "missing_in_etrm", detail: {} };
  assert.equal(differenceText(volume, t), 'eod.detail.volume{"captured":"7440","etrm":"7750"}');
  assert.equal(differenceText(missing, t), "");
  assert.equal(unacknowledged([volume, missing], { a: "seen" }), 1);
  assert.equal(unacknowledged([volume, missing], { a: "seen", b: "late broker deal" }), 0);
  assert.equal(unacknowledged([volume], { a: "  " }), 1);
});

test("both locales carry every deal capture string", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const ours = Object.keys(en).filter((key) => key.startsWith("deals.") || key.startsWith("eod."));
  assert.ok(ours.length > 100);
  for (const key of ours) assert.ok(zh[key], key);
  assert.equal(zh["deals.status_estimate"], "交易台估算，ETRM 日结前");
});
