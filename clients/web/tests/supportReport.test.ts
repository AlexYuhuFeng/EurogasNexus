import assert from "node:assert/strict";
import test from "node:test";

import { safePage, supportClientContext } from "../src/app/model/supportReport.ts";

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
    schemaRevision: "0055_desk_operations",
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
    "client_version", "data_status", "failed_reads", "host", "language", "page",
    "schema_revision", "server_version", "user_agent", "viewport",
  ]);
});
