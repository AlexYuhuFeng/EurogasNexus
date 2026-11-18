import assert from "node:assert/strict";
import test from "node:test";

import {
  clearReadCache,
  invalidateReads,
  loadRead,
  MAX_ENTRIES,
  peekRead,
  readKey,
  setReadCacheScope,
} from "../src/app/data/readCache.ts";

// The read cache (UX_REFERENCE rule 19): the last answer at once, a fresh one behind it, the last
// good answer kept on failure, nothing shared between principals.

test("a key names the endpoint and its parameters in a stable order", () => {
  assert.equal(readKey("/portfolio/ladder", { months: 6, book: "", hub: "TTF" }), "/portfolio/ladder?hub=TTF&months=6");
  assert.equal(readKey("/desk/today"), "/desk/today");
});

test("the first read loads; a repeat within the fresh window reuses it; a stale one updates behind it", async () => {
  clearReadCache();
  setReadCacheScope("trader-1");
  let calls = 0;
  const fetcher = async () => ({ value: ++calls });
  const first = loadRead("/x", fetcher, { now: 1000 });
  assert.equal(peekRead("/x").loading, true);
  await first;
  assert.deepEqual(peekRead<{ value: number }>("/x").data, { value: 1 });
  await loadRead("/x", fetcher, { now: Date.now() });
  assert.equal(calls, 1, "a fresh answer is reused");
  invalidateReads();
  const second = loadRead("/x", fetcher);
  const during = peekRead<{ value: number }>("/x");
  assert.equal(during.updating, true, "the old answer stays on screen while the new one is read");
  assert.equal(during.loading, false);
  assert.deepEqual(during.data, { value: 1 });
  await second;
  assert.deepEqual(peekRead<{ value: number }>("/x").data, { value: 2 });
});

test("a failed refresh keeps the last good answer and says so", async () => {
  clearReadCache();
  setReadCacheScope("trader-2");
  await loadRead("/y", async () => "good");
  await loadRead("/y", async () => { throw new Error("timeout"); }, { force: true });
  const kept = peekRead<string>("/y");
  assert.equal(kept.data, "good");
  assert.ok(kept.error instanceof Error);
});

test("another principal never sees the first one's answers", async () => {
  clearReadCache();
  setReadCacheScope("trader-a");
  await loadRead("/z", async () => "a's book");
  setReadCacheScope("trader-b");
  assert.equal(peekRead("/z").data, undefined);
});

test("the cache is bounded", async () => {
  clearReadCache();
  setReadCacheScope("trader-c");
  for (let index = 0; index < MAX_ENTRIES + 10; index += 1) await loadRead(`/k${index}`, async () => index);
  assert.equal(peekRead("/k0").data, undefined, "the least recently used answer is dropped");
  assert.equal(peekRead(`/k${MAX_ENTRIES + 9}`).data, MAX_ENTRIES + 9);
});
