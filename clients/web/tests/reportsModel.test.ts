/** Research → Reports: the request the form sends and the subject a "Report" link carries. */
import assert from "node:assert/strict";
import test from "node:test";

import {
  parseHubs,
  reportRequestFromForm,
  reportSubjectFromSearch,
  reportSubjectSearch,
  type ReportForm,
} from "../src/app/model/reportsModel.ts";

const form: ReportForm = {
  kind: "daily", variant: "eod", audience: "shareable", sections: null, hubs: "ttf, etf  nbp,ttf",
  periodStart: "", periodEnd: "", subject: null, question: "",
};

test("a daily request carries the edition, the sections and the hubs as typed (ETF stays ETF)", () => {
  const body = reportRequestFromForm(form, "standard", ["prices", "storage"], "en");
  assert.deepEqual(body, { kind: "daily", audience: "shareable", sections: ["prices", "storage"], language: "en", variant: "eod", hubs: ["TTF", "ETF", "NBP"] });
  assert.deepEqual(parseHubs(""), []);
});

test("an asked report sends the question and the edited plan; a situation sends its subject", () => {
  const ask = reportRequestFromForm({ ...form, question: "  Storage versus last year  ", periodStart: "2026-11-09", periodEnd: "2026-11-15" }, "ask", ["storage"], "zh-CN");
  assert.equal(ask.kind, "ask");
  assert.equal(ask.question, "Storage versus last year");
  assert.equal(ask.period_start, "2026-11-09");
  assert.equal(ask.variant, undefined);
  const situation = reportRequestFromForm({ ...form, kind: "situation", subject: { kind: "outage", id: "umm-7" } }, "standard", ["situation_event"], "en");
  assert.equal(situation.outage_id, "umm-7");
  assert.equal(situation.alert_id, undefined);
});

test("a Report link opens Research → Reports on that subject and nothing else reads as one", () => {
  const search = reportSubjectSearch("workspace=market&task=overview&gasDay=2026-11-16&view=x", { kind: "alert", id: "a:1" });
  const params = new URLSearchParams(search);
  assert.equal(params.get("workspace"), "research");
  assert.equal(params.get("task"), "reports");
  assert.equal(params.get("gasDay"), "2026-11-16");
  assert.equal(params.get("view"), null);
  assert.deepEqual(reportSubjectFromSearch(`?${search}`), { kind: "alert", id: "a:1" });
  assert.equal(reportSubjectFromSearch("?workspace=market&subject=alert:1"), null);
  assert.equal(reportSubjectFromSearch("?workspace=research&task=reports&subject=trade:1"), null);
});
