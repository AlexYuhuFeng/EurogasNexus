import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import test from "node:test";
import vm from "node:vm";
import { loadWorkspaceEndpoint } from "../src/stores/workspaceLoading.ts";

/** The client's read lanes, loaded from its source as the other client tests load it. */
function loadLanes(): { acquireReadLane: (signal?: AbortSignal) => Promise<() => void>; MAX_READS_IN_FLIGHT: number } {
  const source = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8")
    .replace(
      /^import \{ HOST_COMMANDS, resolveHostKind, tryHostCommand \} from "@\/app\/host\/hostCapabilities";$/m,
      'const HOST_COMMANDS = {}; const resolveHostKind = () => "browser"; const tryHostCommand = async () => null;',
    )
    .replace("import.meta.env.VITE_EUROGAS_API_BASE_URL", "undefined");
  const executable = stripTypeScriptTypes(source).replace(/^export\s+/gm, "");
  const sandbox: Record<string, unknown> = {
    AbortController, URL, URLSearchParams, console, DOMException, setTimeout, clearTimeout,
    localStorage: { getItem: () => null, removeItem: () => undefined, setItem: () => undefined },
    window: { location: { origin: "https://example.test" } },
  };
  vm.runInNewContext(
    `${executable}\nglobalThis.__lanes = { acquireReadLane, MAX_READS_IN_FLIGHT };`,
    sandbox,
    { filename: "client.ts" },
  );
  return sandbox.__lanes as ReturnType<typeof loadLanes>;
}

const { acquireReadLane, MAX_READS_IN_FLIGHT } = loadLanes();

test("reads beyond the lane count wait in order and leave when a lane is given back", async () => {
  const held = await Promise.all(Array.from({ length: MAX_READS_IN_FLIGHT }, () => acquireReadLane()));
  const order: number[] = [];
  const first = acquireReadLane().then((release) => { order.push(1); return release; });
  const second = acquireReadLane().then((release) => { order.push(2); return release; });
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.deepEqual(order, [], "no lane is free yet");
  held[0]!();
  held[0]!(); // giving a lane back twice frees it once
  const releaseFirst = await first;
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.deepEqual(order, [1]);
  held[1]!();
  const releaseSecond = await second;
  assert.deepEqual(order, [1, 2]);
  for (const release of [...held.slice(2), releaseFirst, releaseSecond]) release();
});

test("a queued read that is aborted leaves the queue with an AbortError", async () => {
  const held = await Promise.all(Array.from({ length: MAX_READS_IN_FLIGHT }, () => acquireReadLane()));
  const controller = new AbortController();
  const waiting = acquireReadLane(controller.signal);
  controller.abort();
  await assert.rejects(waiting, (error: unknown) => (error as { name?: string }).name === "AbortError");
  for (const release of held) release();
  // The lanes are all free again.
  const again = await Promise.all(Array.from({ length: MAX_READS_IN_FLIGHT }, () => acquireReadLane()));
  for (const release of again) release();
});

test("a workspace read's bound starts when it leaves for the server, not while it waits", async () => {
  const outcome = await loadWorkspaceEndpoint<string>(
    async ({ onDispatch } = {}) => {
      // Waits 40 ms for a lane (longer than the 25 ms bound), then answers in 5 ms.
      await new Promise((resolve) => setTimeout(resolve, 40));
      onDispatch?.();
      await new Promise((resolve) => setTimeout(resolve, 5));
      return "answered";
    },
    { retries: 0, timeoutMs: 25 },
  );
  assert.deepEqual(outcome, { ok: true, value: "answered" });

  const slow = await loadWorkspaceEndpoint<string>(
    ({ onDispatch, signal } = {}) => new Promise((resolve, reject) => {
      onDispatch?.();
      const timer = setTimeout(() => resolve("late"), 200);
      signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
      });
    }),
    { retries: 0, timeoutMs: 25 },
  );
  assert.equal(slow.ok, false);
  assert.equal(!slow.ok && slow.error.code, "timeout");
});
