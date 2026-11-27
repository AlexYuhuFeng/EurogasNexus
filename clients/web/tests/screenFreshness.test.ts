/**
 * Small-desk plan 3.7: when the feed, the server or the browser's connection drops, the screen
 * says it is not current (with the time it was last known good), and nothing else changes; and
 * this browser's clock is measured against the server's (app/data/screenFreshness.ts).
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  CLOCK_SKEW_WARN_MS,
  LIVE_QUIET_STALE_MS,
  clockSkewed,
  probeDelayMs,
  screenFreshnessOf,
  skewMs,
  type ConnectionState,
} from "../src/app/data/screenFreshness.ts";
import type { LiveStatus } from "../src/app/data/liveStream.ts";

const NOW = Date.parse("2026-11-27T09:00:00Z");
const fine: ConnectionState = {
  browserOnline: true,
  serverReachable: true,
  lastContactAt: NOW - 2_000,
  unreachableSince: null,
  clockSkewMs: null,
  serverClock: null,
};
const live: LiveStatus = { state: "live", lastEventAt: NOW - 1_000, lastChangeAt: null, retryAt: null };

test("a reachable server and a live stream: the screen is current", () => {
  assert.deepEqual(screenFreshnessOf(fine, live, NOW), { current: true });
  // A refused stream (pages re-read on a timer) is not stale.
  assert.deepEqual(screenFreshnessOf(fine, { ...live, state: "paused", lastEventAt: NOW - 600_000 }, NOW), { current: true });
});

test("the server not answering: stale since the last answer", () => {
  const down = { ...fine, serverReachable: false, unreachableSince: NOW - 1_000 };
  assert.deepEqual(screenFreshnessOf(down, live, NOW), { current: false, reason: "server_unreachable", since: NOW - 2_000 });
});

test("the browser offline wins over everything else", () => {
  const offline = { ...fine, browserOnline: false, serverReachable: false };
  const freshness = screenFreshnessOf(offline, live, NOW);
  assert.equal(freshness.current, false);
  assert.equal(!freshness.current && freshness.reason, "browser_offline");
});

test("a dropped live connection is stale only after its quiet allowance", () => {
  const dropped: LiveStatus = { ...live, state: "offline", lastEventAt: NOW - LIVE_QUIET_STALE_MS + 1_000 };
  assert.deepEqual(screenFreshnessOf(fine, dropped, NOW), { current: true }); // a brief blip: no flicker
  const quiet: LiveStatus = { ...dropped, lastEventAt: NOW - LIVE_QUIET_STALE_MS - 1_000 };
  assert.deepEqual(screenFreshnessOf(fine, quiet, NOW), { current: false, reason: "live_quiet", since: quiet.lastEventAt });
});

test("the browser's clock is measured at the middle of the round trip", () => {
  // Sent at 0, answered at 400 ms: the server's stamp belongs to 200 ms.
  const sent = NOW;
  const received = NOW + 400;
  assert.equal(skewMs(new Date(NOW + 200).toISOString(), sent, received), 0);
  assert.equal(skewMs(new Date(NOW + 200 - 7_000).toISOString(), sent, received), 7_000);
  assert.equal(skewMs(null, sent, received), null);
  assert.equal(clockSkewed({ ...fine, clockSkewMs: CLOCK_SKEW_WARN_MS + 1 }), true);
  assert.equal(clockSkewed({ ...fine, clockSkewMs: -CLOCK_SKEW_WARN_MS }), false);
  assert.equal(CLOCK_SKEW_WARN_MS, 5_000);
});

test("an unreachable server is asked again at 5 s doubling to 30 s", () => {
  assert.deepEqual([1, 2, 3, 4, 5].map(probeDelayMs), [5_000, 10_000, 20_000, 30_000, 30_000]);
});
