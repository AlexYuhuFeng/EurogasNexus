import assert from "node:assert/strict";
import test from "node:test";

import {
  REPORT_CATEGORIES,
  REPORT_PROBLEM_EVENT,
  SUGGESTION_CATEGORY,
  requestFeedback,
  safePage,
  supportClientContext,
} from "../src/app/model/supportReport.ts";

test("the page keeps navigation parameters and drops record ids", () => {
  assert.equal(
    safePage({ pathname: "/", search: "?workspace=contracts&task=exposure&contract=SECRET-1&gasDay=2026-11-02" }),
    "/?workspace=contracts&task=exposure",
  );
  assert.equal(safePage({ pathname: "/", search: "" }), "/");
});

test("client context is allowlisted and bounded", () => {
  const context = supportClientContext({
    clientVersion: "0.7.0",
    serverVersion: "0.7.0",
    schemaRevision: "0056_hedge_approvals",
    hostKind: "browser",
    language: "en",
    location: { pathname: "/", search: "?workspace=market" },
    viewport: { width: 1366, height: 768, devicePixelRatio: 1.25 },
    userAgent: "x".repeat(500),
    dataStatus: "partial",
    endpointErrorCodes: { "/market/quotes": "HTTP_503 abc123" },
  });
  assert.equal(context.viewport, "1366x768@1.25x");
  assert.equal((context.user_agent as string).length, 200);
  assert.deepEqual(context.failed_reads, [{ endpoint: "/market/quotes", code: "HTTP_503 abc123" }]);
  assert.deepEqual(Object.keys(context).sort(), [
    "client_version", "composition", "data_status", "failed_reads", "host", "language", "page",
    "schema_revision", "server_version", "user_agent", "viewport",
  ]);
});

test("AIR-2: feedback is a suggestion report that carries the role composition", () => {
  assert.ok(REPORT_CATEGORIES.includes(SUGGESTION_CATEGORY));
  const context = supportClientContext({
    clientVersion: null, serverVersion: null, schemaRevision: null, hostKind: "browser",
    language: "zh", location: { pathname: "/", search: "" },
    viewport: { width: 390, height: 844, devicePixelRatio: 3 }, userAgent: "",
    dataStatus: null, endpointErrorCodes: {}, composition: "lng",
  });
  assert.equal(context.composition, "lng");

  const seen: unknown[] = [];
  const target = new EventTarget();
  target.addEventListener(REPORT_PROBLEM_EVENT, (event) => seen.push((event as CustomEvent).detail));
  const previous = (globalThis as { window?: unknown }).window;
  (globalThis as { window?: unknown }).window = target;
  try {
    requestFeedback("trader");
  } finally {
    (globalThis as { window?: unknown }).window = previous;
  }
  assert.deepEqual(seen, [{ category: "suggestion", severity: "P4", composition: "trader" }]);
});

test("AIR-2: every report category has an EN and a ZH label", async () => {
  const { readFile } = await import("node:fs/promises");
  for (const locale of ["en", "zh"]) {
    const strings = JSON.parse(await readFile(new URL(`../src/i18n/${locale}.json`, import.meta.url), "utf-8"));
    for (const category of REPORT_CATEGORIES) assert.ok(strings[`support.category_${category}`], `${locale} ${category}`);
    assert.ok(strings["topbar.send_feedback"] && strings["feedback.send"]);
  }
});
