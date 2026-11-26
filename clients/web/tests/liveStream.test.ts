/**
 * The live stream (app/data/liveStream.ts): one connection for the topics pages subscribe to,
 * resumed from the last event id after a drop, with a published state (live, stale, offline)
 * that the top bar shows with the time of the last update. And the throttle that coalesces a
 * burst of notices into a leading and a trailing re-read (app/hooks/useLive.ts).
 */
import assert from "node:assert/strict";
import test, { after, beforeEach, mock } from "node:test";

import { AUTHENTICATED_AUTH_STATE } from "../src/stores/workspaceLoading.ts";
import { apiRegistry } from "./support/mockApiClient.ts";
import { closeApiStoreHarness, loadApiStore, settle } from "./support/apiStoreHarness.ts";

type LiveModule = typeof import("../src/app/data/liveStream.ts");
type UseLiveModule = typeof import("../src/app/hooks/useLive.ts");

after(closeApiStoreHarness);

interface Opened {
  path: string;
  handlers: Record<string, (payload: unknown) => void>;
  onStatus?: (status: "open" | "error") => void;
  closed: boolean;
}

let live: LiveModule;
let opened: Opened[] = [];

async function liveModule(): Promise<LiveModule> {
  const harness = await loadApiStore();
  return harness.load<LiveModule>("/src/app/data/liveStream.ts");
}

function open(path: string, handlers: Record<string, (payload: unknown) => void>, onStatus?: (status: "open" | "error") => void) {
  const entry: Opened = { path, handlers, onStatus, closed: false };
  opened.push(entry);
  return {
    close: () => {
      entry.closed = true;
    },
  };
}

function current(): Opened {
  const entry = opened.filter((item) => !item.closed).at(-1);
  assert.ok(entry, "a connection is open");
  return entry;
}

function params(entry: Opened): URLSearchParams {
  return new URLSearchParams(entry.path.split("?")[1]);
}

beforeEach(async () => {
  live ??= await liveModule();
  // Close the last test's timers on the clock that made them, then start a fresh clock.
  live.resetLiveStreamForTests();
  mock.timers.reset();
  mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-26T09:00:00Z") });
  opened = [];
  live.resetLiveStreamForTests({ open: open as never, clock: () => Date.now(), jitter: () => 0.5 });
});

test("the backoff doubles from one second to thirty, with a fifth either way of jitter", () => {
  assert.equal(live.liveBackoffMs(1, 0.5), 1_000);
  assert.equal(live.liveBackoffMs(2, 0.5), 2_000);
  assert.equal(live.liveBackoffMs(5, 0.5), 16_000);
  assert.equal(live.liveBackoffMs(6, 0.5), 30_000);
  assert.equal(live.liveBackoffMs(20, 0.5), 30_000);
  assert.equal(live.liveBackoffMs(1, 0), 800);
  assert.equal(live.liveBackoffMs(1, 1), 1_200);
});

test("nothing opens until the session turns it on and a page subscribes; then one connection carries every topic", () => {
  const stopPrices = live.subscribeLive("prices", () => undefined);
  mock.timers.tick(100);
  assert.equal(opened.length, 0, "off until an authenticated session turns it on");
  live.setLiveEnabled(true);
  assert.equal(opened.length, 1);
  assert.equal(params(current()).get("topics"), "prices");
  assert.equal(live.liveStatus().state, "connecting");

  // A second page's topics are asked for on the same stream (one re-open, after a short debounce).
  const stopAlerts = live.subscribeLive("alerts", () => undefined);
  live.subscribeLive("trades", () => undefined);
  mock.timers.tick(60);
  assert.equal(opened.length, 2);
  assert.equal(opened[0].closed, true);
  assert.equal(params(current()).get("topics"), "alerts,prices,trades");

  current().handlers.ready({ topics: ["alerts", "prices", "trades"], event_id: "live|2026-11-26T09:00:00+00:00" });
  assert.equal(live.liveStatus().state, "live");

  stopPrices();
  stopAlerts();
  mock.timers.tick(60);
  assert.equal(params(current()).get("topics"), "trades");
  assert.equal(params(current()).get("last_event_id"), "live|2026-11-26T09:00:00+00:00", "a re-open resumes");
});

test("a change reaches only its topic's listeners and moves the last-change time", () => {
  const prices: unknown[] = [];
  const alerts: unknown[] = [];
  live.subscribeLive("prices", (change) => prices.push(change));
  live.subscribeLive("alerts", (change) => alerts.push(change));
  live.setLiveEnabled(true);
  mock.timers.tick(60);
  current().handlers.ready({ event_id: "live|a" });
  current().handlers.change({ topic: "prices", changed_at: "2026-11-26T08:59:58Z", event_id: "live|b" });
  assert.equal(prices.length, 1);
  assert.equal(alerts.length, 0);
  assert.equal(live.liveStatus().lastChangeAt, Date.parse("2026-11-26T08:59:58Z"));
});

test("a drop goes offline with the retry time, and the reconnect resumes from the last event id", () => {
  live.subscribeLive("prices", () => undefined);
  live.setLiveEnabled(true);
  current().handlers.ready({ event_id: "live|one" });
  current().handlers.heartbeat({ at: "x", event_id: "live|two" });
  const heardAt = live.liveStatus().lastEventAt;

  current().onStatus?.("error");
  const status = live.liveStatus();
  assert.equal(status.state, "offline");
  assert.equal(status.retryAt, Date.now() + 1_000);
  assert.equal(status.lastEventAt, heardAt, "the time of the last update stays for the indicator");
  assert.equal(opened.filter((item) => !item.closed).length, 0);

  mock.timers.tick(1_000);
  assert.equal(params(current()).get("last_event_id"), "live|two");
  // Still failing: the next wait doubles.
  current().onStatus?.("error");
  assert.equal(live.liveStatus().retryAt, Date.now() + 2_000);
  mock.timers.tick(2_000);
  current().handlers.ready({ event_id: "live|three" });
  assert.equal(live.liveStatus().state, "live");
  // A ready resets the backoff.
  current().onStatus?.("error");
  assert.equal(live.liveStatus().retryAt, Date.now() + 1_000);
});

test("an open connection that goes silent is stale, is re-opened, and is live again when heard", () => {
  live.subscribeLive("prices", () => undefined);
  live.setLiveEnabled(true);
  current().handlers.ready({ event_id: "live|one" });
  mock.timers.tick(live.LIVE_STALE_AFTER_MS - 1_000);
  assert.equal(live.liveStatus().state, "live");
  mock.timers.tick(2_000);
  assert.equal(live.liveStatus().state, "stale");
  assert.equal(opened[0].closed, true, "the half-dead connection is closed");
  mock.timers.tick(1_000);
  assert.equal(opened.length, 2);
  assert.equal(live.liveStatus().state, "stale", "still stale until the new connection is heard");
  current().handlers.heartbeat({ event_id: "live|two" });
  assert.equal(live.liveStatus().state, "live");
});

test("a store the server cannot read says stale; a late callback of a closed connection changes nothing", () => {
  live.subscribeLive("prices", () => undefined);
  live.setLiveEnabled(true);
  const first = current();
  first.handlers.ready({ event_id: "live|one" });
  first.handlers.warning({ message: "unavailable" });
  assert.equal(live.liveStatus().state, "stale");
  first.handlers.heartbeat({ event_id: "live|two" });
  assert.equal(live.liveStatus().state, "live");

  live.subscribeLive("alerts", () => undefined);
  mock.timers.tick(60);
  assert.equal(first.closed, true);
  first.onStatus?.("error");
  assert.notEqual(live.liveStatus().state, "offline", "the old connection's error is not this one's");
});

test("revoked ends the stream; turning it off forgets the position so another identity starts afresh", () => {
  live.subscribeLive("prices", () => undefined);
  live.setLiveEnabled(true);
  current().handlers.ready({ event_id: "live|mine" });
  current().handlers.revoked({ reason: "SESSION_REVOKED" });
  assert.equal(live.liveStatus().state, "idle");
  assert.equal(opened.filter((item) => !item.closed).length, 0);
  mock.timers.tick(60_000);
  assert.equal(opened.filter((item) => !item.closed).length, 0, "no reconnect after a revocation");

  live.setLiveEnabled(true);
  current().handlers.ready({ event_id: "live|theirs" });
  live.setLiveEnabled(false);
  assert.equal(live.liveStatus().lastEventAt, null);
  live.setLiveEnabled(true);
  assert.equal(params(current()).get("last_event_id"), null);
});

test("jobs events reach job listeners with their shape", () => {
  const jobs: { job_id: string; progress: number }[] = [];
  live.subscribeLive("jobs", (job) => jobs.push(job));
  live.setLiveEnabled(true);
  assert.equal(params(current()).get("topics"), "jobs");
  current().handlers.jobs({ job_id: "job-1", kind: "BACKTEST", status: "RUNNING", progress: 0.4, step: null, event_id: "live|j" });
  current().handlers.jobs({ nonsense: true });
  assert.deepEqual(jobs.map((job) => [job.job_id, job.progress]), [["job-1", 0.4]]);
});

test("the throttle reads at once, then once at the end of the interval however many notices came", async () => {
  const { createThrottle } = await (await loadApiStore()).load<UseLiveModule>("/src/app/hooks/useLive.ts");
  let clock = 0;
  const timers: { fn: () => void; at: number }[] = [];
  let fired = 0;
  const throttle = createThrottle(
    () => (fired += 1),
    2_000,
    () => clock,
    {
      set: (fn, ms) => {
        const timer = { fn, at: clock + ms };
        timers.push(timer);
        return timer;
      },
      clear: (handle) => timers.splice(timers.indexOf(handle as (typeof timers)[number]), 1),
    },
  );
  throttle.call();
  assert.equal(fired, 1, "the first notice reads at once");
  clock = 100;
  throttle.call();
  throttle.call();
  throttle.call();
  assert.equal(fired, 1);
  assert.equal(timers.length, 1, "one trailing read for the burst");
  assert.equal(timers[0].at, 2_000);
  clock = 2_000;
  timers.shift()!.fn();
  assert.equal(fired, 2);
  clock = 5_000;
  throttle.call();
  assert.equal(fired, 3, "after a quiet interval the next notice reads at once again");
  clock = 5_100;
  throttle.call();
  throttle.cancel();
  assert.equal(timers.length, 0);
});

test("the store turns the live stream on with the decision streams and off at every identity change", async () => {
  // The store's reads settle on real timers.
  mock.timers.reset();
  const harness = await loadApiStore();
  // The store's import resolves to the same module instance the test drives.
  live.resetLiveStreamForTests();
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  harness.answer("me", () => ({ data: { principal_id: "p", roles: ["trader"], permissions: ["market.read"] }, meta: {} }));
  await harness.store.getState().fetchMe();
  const stop = live.subscribeLive("prices", () => undefined);
  harness.store.getState().subscribeDecisionStreams();
  const registry = apiRegistry();
  const livePath = () => Object.keys(registry.streams).find((path) => path.startsWith("/stream/live?"));
  assert.match(livePath() ?? "", /topics=prices/);
  harness.answer("me", () => Promise.reject(new Error("API 401: session expired")));
  await harness.store.getState().fetchMe();
  await settle();
  assert.equal(livePath(), undefined, "no live stream survives the identity that opened it");
  assert.equal(live.liveStatus().state, "idle");
  stop();
});
