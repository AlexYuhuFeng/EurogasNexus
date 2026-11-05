/** Server-sent events read over fetch (desktop sessions keep their credential in a header). */
import assert from "node:assert/strict";
import test from "node:test";
import { dispatchSseBlock } from "../src/api/sse.ts";

test("an SSE block reaches its named handler, parsed as JSON when it is JSON", () => {
  const seen: unknown[] = [];
  dispatchSseBlock("event: market\ndata: {\"hub\":\"NBP\"}", { market: (data) => seen.push(data) });
  dispatchSseBlock(": keep-alive", { message: (data) => seen.push(data) });
  dispatchSseBlock("data: line one\ndata: line two", { message: (data) => seen.push(data) });
  dispatchSseBlock("event: other\ndata: 1", { market: (data) => seen.push(data) });
  assert.deepEqual(seen, [{ hub: "NBP" }, "line one\nline two"]);
});
