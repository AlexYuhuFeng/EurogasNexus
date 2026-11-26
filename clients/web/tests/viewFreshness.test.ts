import assert from "node:assert/strict";
import test, { after, mock } from "node:test";

import type { DeskTodayDTO } from "../src/api/client.ts";
import { REFRESHING_SHOWN_MS, clearViewFreshness, noteViewMeta, refreshingSince } from "../src/app/data/viewFreshness.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

// A heavy read may answer from the server's kept result while it is recomputed
// (application/warm_views.py). The page shows it, the top bar says from when, and fresh
// figures replace it without a loading state.

after(closeApiStoreHarness);

const refreshing = (at: string) => ({ view: { state: "refreshing", computed_at_utc: at, max_age_seconds: 60 } });
const fresh = (at: string) => ({ view: { state: "fresh", computed_at_utc: at, max_age_seconds: 60 } });

test("a kept answer being recomputed is named with its time until a fresh one replaces it", () => {
  clearViewFreshness();
  noteViewMeta("/desk/today", fresh("2026-11-26T09:40:00Z"), 0);
  assert.equal(refreshingSince(), null);
  noteViewMeta("/desk/today", refreshing("2026-11-26T09:41:00Z"), 0);
  noteViewMeta("/reports/catalogue", refreshing("2026-11-26T09:30:00Z"), 0);
  // The oldest figures on screen are the ones named.
  assert.equal(refreshingSince(), "2026-11-26T09:30:00Z");
  noteViewMeta("/reports/catalogue", fresh("2026-11-26T09:42:00Z"), 1);
  assert.equal(refreshingSince(), "2026-11-26T09:41:00Z");
  // An answer with no view meta (a read that is not kept) also clears its path.
  noteViewMeta("/desk/today", {}, 2);
  assert.equal(refreshingSince(), null);
});

test("the note lapses once the server's refresh has had time to finish", () => {
  clearViewFreshness();
  noteViewMeta("/desk/today", refreshing("2026-11-26T09:41:00Z"), 0);
  noteViewMeta("/other", {}, REFRESHING_SHOWN_MS + 1);
  assert.equal(refreshingSince(), null);
});

test("Today re-reads quietly after a kept answer and stops once the answer is fresh", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const { load } = await loadApiStore();
    const desk = await load<typeof import("../src/app/hooks/useDeskToday.ts")>("/src/app/hooks/useDeskToday.ts");
    desk.clearDeskTodayCache();
    const answers = [
      { data: { gas_day: "kept" } as DeskTodayDTO, meta: refreshing("2026-11-26T09:41:00Z") },
      { data: { gas_day: "recomputed" } as DeskTodayDTO, meta: fresh("2026-11-26T09:42:00Z") },
    ];
    let calls = 0;
    const loading: boolean[] = [];
    desk.setDeskTodayFetcher(() => Promise.resolve(answers[Math.min(calls++, answers.length - 1)]));
    const key = desk.deskTodayKey("p-1");
    await desk.loadDeskToday(key);
    assert.equal(desk.deskTodaySnapshot(key).today?.gas_day, "kept");
    assert.equal(calls, 1);
    mock.timers.tick(desk.DESK_TODAY_FOLLOW_UP_MS);
    loading.push(desk.deskTodaySnapshot(key).loading);
    await new Promise((done) => setImmediate(done));
    assert.equal(calls, 2);
    assert.deepEqual(loading, [false], "the follow-up keeps the kept figures without a loading state");
    assert.equal(desk.deskTodaySnapshot(key).today?.gas_day, "recomputed");
    mock.timers.tick(desk.DESK_TODAY_FOLLOW_UP_MS * 3);
    await new Promise((done) => setImmediate(done));
    assert.equal(calls, 2, "a fresh answer asks for no further read");
    desk.clearDeskTodayCache();
  } finally {
    mock.timers.reset();
  }
});
