import assert from "node:assert/strict";
import test from "node:test";

import {
  formatGasDay,
  formatInstant,
  formattingLocale,
  isTimeZonePreference,
  resolveTimeZone,
} from "../src/app/time/timeFormat.ts";
import { dataProblemCount } from "../src/app/model/dataProblems.ts";
import { noticeNames, problemSignature } from "../src/app/model/dataProblems.ts";
import { phoneColumnSplit } from "../src/components/ui/dataGridModel.ts";
import type { EndpointFailureSurface } from "../src/app/model/endpointFailures.ts";

// The shell foundation (docs/product/UX_REFERENCE.md rules 13-17).

const NOW = Date.parse("2026-11-17T01:30:00Z");

test("an instant is shown in the reader's zone with the zone named, the date only when not today", () => {
  const winter = "2026-11-17T00:57:47Z";
  assert.equal(formatInstant(winter, { language: "en", preference: "utc", nowMs: NOW })?.text, "00:57 UTC");
  assert.equal(formatInstant(winter, { language: "en", preference: "market", nowMs: NOW })?.text, "01:57 CET");
  assert.equal(
    formatInstant(winter, { language: "en", preference: "device", deviceZone: "Asia/Shanghai", nowMs: NOW })?.text,
    "08:57 GMT+8",
  );
  // Summer: the market's clock is CEST.
  assert.equal(
    formatInstant("2026-07-01T10:00:00Z", { language: "en", preference: "market", nowMs: Date.parse("2026-07-01T12:00:00Z") })?.text,
    "12:00 CEST",
  );
  // Another day: the date leads, short; seconds only on request.
  const yesterday = formatInstant("2026-11-16T22:57:47Z", { language: "en", preference: "utc", nowMs: NOW, seconds: true });
  assert.equal(yesterday?.text, "16 Nov 22:57:47 UTC");
  // The tooltip names the full instant and its UTC form; dateTime is the UTC instant.
  const market = formatInstant(winter, { language: "en", preference: "market", nowMs: NOW })!;
  assert.match(market.title, /17 Nov 2026,? 01:57:47 CET \(2026-11-17 00:57:47 UTC\)/);
  assert.equal(market.iso, "2026-11-17T00:57:47.000Z");
  assert.equal(formatInstant(null, { language: "en", preference: "utc" }), null);
  assert.equal(formatInstant("not a time", { language: "en", preference: "utc" }), null);
});

test("words and months follow the app's language, never the browser's", () => {
  assert.equal(formattingLocale("zh-CN"), "zh-CN");
  assert.equal(formattingLocale("en"), "en-GB");
  const zh = formatInstant("2026-11-16T22:57:47Z", { language: "zh-CN", preference: "utc", nowMs: NOW })!;
  assert.match(zh.text, /^11月16日 22:57 UTC$/);
  assert.equal(formatGasDay("2026-12-01", "en"), "1 Dec");
  assert.equal(formatGasDay("2026-12-01", "zh-CN"), "12月1日");
  // A gas day is not an instant: no zone moves it.
  assert.equal(formatGasDay("2026-11-16", "en", true), "16 Nov 2026");
});

test("the preference resolves to a zone and rejects anything else", () => {
  assert.equal(resolveTimeZone("utc"), "UTC");
  assert.equal(resolveTimeZone("market"), "Europe/Berlin");
  assert.equal(resolveTimeZone("device", "America/New_York"), "America/New_York");
  assert.ok(isTimeZonePreference("device"));
  assert.equal(isTimeZonePreference("Europe/Paris"), false);
});

test("a DataGrid keeps its primary columns on a phone and folds the rest into Details", () => {
  const columns = [
    { id: "hub", header: "Hub", rowHeader: true },
    { id: "bid", header: "Bid" },
    { id: "mid", header: "Mid" },
    { id: "tick", header: "Tick" },
    { id: "bar", header: "", decorative: true },
  ];
  const split = phoneColumnSplit(columns, 3);
  assert.deepEqual(split.visible.map((column) => column.id), ["hub", "bid", "mid"]);
  // A decorative column is not repeated as a detail.
  assert.deepEqual(split.folded.map((column) => column.id), ["tick"]);
  const declared = phoneColumnSplit(
    [
      { id: "hub", header: "Hub", rowHeader: true },
      { id: "bid", header: "Bid" },
      { id: "reason", header: "Reason", priority: "primary" as const },
    ],
    3,
  );
  assert.deepEqual(declared.visible.map((column) => column.id), ["hub", "reason"]);
});

function failures(keys: string[], total = keys.length): EndpointFailureSurface {
  const entries = keys.map((key) => ({ key, labelKey: key, label: `L-${key}`, code: "timeout" as const, codeKey: "", message: "" }));
  return {
    total,
    entries,
    hiddenCount: total - keys.length,
    truncated: total > keys.length,
    summaryKey: "",
    summary: "",
    truncatedSummaryKey: null,
    truncatedSummary: null,
  };
}

test("a set of problems has one identity, so a dismissal holds until the set changes", () => {
  assert.equal(problemSignature(failures(["storage", "flows"])), problemSignature(failures(["flows", "storage"])));
  assert.notEqual(problemSignature(failures(["flows"])), problemSignature(failures(["flows", "lng"])));
  assert.equal(problemSignature(failures([])), "");
  const t = (key: string, options?: Record<string, unknown>) => `${key}(${options?.names}|${options?.count})`;
  assert.equal(noticeNames(failures(["a", "b"]), t), "L-a, L-b");
  assert.equal(noticeNames(failures(["a", "b", "c", "d", "e"], 7), t), "status.notice_more(L-a, L-b, L-c|4)");
  assert.equal(dataProblemCount({ endpointFailures: 5, staleFigures: 2, sourceIssues: 0 }), 7);
});

test("a failed read says what happened: not permitted, missing, server failure, unreachable", async () => {
  const { requestFailureCode } = await import("../src/stores/workspaceLoading.ts");
  assert.equal(requestFailureCode({ status: 403 }), "forbidden");
  assert.equal(requestFailureCode({ status: 401 }), "forbidden");
  assert.equal(requestFailureCode({ status: 404 }), "not_found");
  assert.equal(requestFailureCode({ status: 503 }), "server");
  assert.equal(requestFailureCode({ status: 422 }), "request");
  assert.equal(requestFailureCode(new TypeError("Failed to fetch")), "network");
});
