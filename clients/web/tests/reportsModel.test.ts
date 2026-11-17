/** Research → Reports: the request the form sends and the subject a "Report" link carries. */
import assert from "node:assert/strict";
import test from "node:test";

import {
  annexByDefault,
  editedByLabel,
  elapsedLabel,
  explainFailure,
  formIssues,
  parseHubs,
  REPORT_STAGES,
  reportPeriodLabel,
  reportStageAt,
  sendableSections,
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

test("the form knows before Generate what the server would refuse", () => {
  const catalogue = {
    hubs: ["TTF", "NBP", "THE"],
    availability: {
      can_generate: true, reason: null, sections: {}, audiences: { internal: { allowed: true, reason: null }, shareable: { allowed: true, reason: null } },
      period: { max_days: 400, latest_end: "2026-11-18" }, ai: { available: false, reason: "off" }, languages: ["en", "zh-CN"] as ("en" | "zh-CN")[],
    },
  };
  const ok = { ...form, hubs: "ttf", periodStart: "2026-11-01", periodEnd: "2026-11-07" };
  assert.deepEqual(formIssues(ok, "standard", ["prices"], catalogue, "2026-11-18"), []);
  const keys = (f: typeof form, sections = ["prices"]) => formIssues(f, "standard", sections, catalogue, "2026-11-18").map((i) => i.key);
  assert.deepEqual(keys({ ...ok, periodEnd: "2026-10-01" }), ["reports.issue.period_order"]);
  assert.deepEqual(keys({ ...ok, periodStart: "2024-01-01" }), ["reports.issue.period_long"]);
  assert.deepEqual(keys({ ...ok, periodEnd: "2026-12-01" }), ["reports.issue.period_future"]);
  assert.deepEqual(keys({ ...ok, hubs: "TTFX" }), ["reports.issue.hub"]);
  assert.deepEqual(keys(ok, []), ["reports.issue.no_sections"]);
  const viewer = { ...catalogue, availability: { ...catalogue.availability, can_generate: false, reason: "role" } };
  assert.deepEqual(formIssues(ok, "standard", ["prices"], viewer, "2026-11-18").map((i) => i.key), ["reports.issue.role"]);
  assert.deepEqual(formIssues({ ...ok, question: "" }, "ask", [], catalogue, "2026-11-18").map((i) => i.key), ["reports.issue.question"]);
});

test("a report for distribution never sends a book section", () => {
  const offered = [{ key: "prices" }, { key: "storage" }];
  assert.deepEqual(sendableSections(["prices", "book_position", "storage"], offered), ["prices", "storage"]);
});

test("a failure says what failed and offers what helps", () => {
  assert.deepEqual(explainFailure(null, null, true), { key: "reports.fail.cancelled", retry: true, withoutAi: false });
  assert.equal(explainFailure(403, "identity_role_forbidden", false).key, "reports.fail.forbidden");
  assert.equal(explainFailure(422, "licensed_data_not_redistributable", false).key, "reports.licensed_refused");
  assert.deepEqual(explainFailure(null, null, false), { key: "reports.fail.timeout", retry: true, withoutAi: true });
  assert.equal(explainFailure(503, "runtime_db_unavailable", false).key, "reports.fail.store");
  assert.equal(elapsedLabel(83_400), "1:23");
});
