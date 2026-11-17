/** Research → Reports: the request the form sends and the subject a "Report" link carries. */
import assert from "node:assert/strict";
import test from "node:test";

import {
  annexByDefault,
  editedByLabel,
  parseHubs,
  REPORT_STAGES,
  reportPeriodLabel,
  reportStageAt,
  reportRequestFromForm,
  reportSubjectFromSearch,
  reportSubjectSearch,
  type ReportForm,
} from "../src/app/model/reportsModel.ts";

const form: ReportForm = {
  kind: "daily", variant: "eod", audience: "shareable", sections: null, hubs: "ttf, etf  nbp,ttf",
  periodStart: "", periodEnd: "", subject: null, question: "", annex: null,
};

test("a daily request carries the edition, the sections and the hubs as typed (ETF stays ETF)", () => {
  const body = reportRequestFromForm(form, "standard", ["prices", "storage"], "en");
  assert.deepEqual(body, { kind: "daily", audience: "shareable", sections: ["prices", "storage"], language: "en", variant: "eod", hubs: ["TTF", "ETF", "NBP"] });
  assert.deepEqual(parseHubs(""), []);
});

test("the data annex is sent only when it differs from the kind's default", () => {
  assert.equal(annexByDefault("daily"), false);
  assert.equal(annexByDefault("weekly"), true);
  assert.equal(reportRequestFromForm({ ...form, annex: true }, "standard", [], "en").annex, true);
  assert.equal(reportRequestFromForm({ ...form, annex: false }, "standard", [], "en").annex, undefined);
  assert.equal(reportRequestFromForm({ ...form, kind: "weekly", annex: false }, "standard", [], "en").annex, false);
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

test("the viewer's CSV comes from the report's own data block; summary hides the body", async () => {
  const { reportCsv, summaryOnlyHtml } = await import("../src/app/model/reportsModel.ts");
  const html = '<html><head></head><body><script type="application/json" id="report-data">'
    + '{"report_id":"mr-1","tables":[{"section":"storage","caption":"Fill (%)","columns":["day","fill"],'
    + '"rows":[{"day":"2026-11-15","fill":72.6},{"day":"2026-11-14","fill":null}]}]}</script></body></html>';
  assert.equal(reportCsv(html), "storage: Fill (%)\nday,fill\n2026-11-15,72.6\n2026-11-14,");
  assert.equal(reportCsv("<html></html>"), "");
  assert.match(summaryOnlyHtml(html), /\.r-body,\.r-back-sheet\{display:none!important\}<\/style><\/head>/);
});

test("generation stages advance in order and hold at laying out until the reply", () => {
  assert.deepEqual(REPORT_STAGES, ["planning", "collecting", "writing", "checking", "laying_out"]);
  const seen = [0, 2_000, 10_000, 50_000, 120_000].map(reportStageAt);
  assert.deepEqual(seen, ["collecting", "collecting", "writing", "checking", "laying_out"]);
});

test("the stored list shows the period and who edited the report", () => {
  assert.equal(reportPeriodLabel("2026-11-09", "2026-11-15"), "9 Nov – 15 Nov");
  assert.equal(reportPeriodLabel(null, "2026-11-15"), "15 Nov");
  assert.equal(reportPeriodLabel(null, null), "");
  assert.equal(editedByLabel({ edited_by: "model" }), "model");
  assert.equal(editedByLabel({}), "rule");
});
