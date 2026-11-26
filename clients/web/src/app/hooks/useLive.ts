/**
 * Live data for a page (app/data/liveStream.ts): its state, and re-reads on change notices.
 *
 * `useLiveTopics(topics, reload)` re-reads when a subscribed topic changes, at most once per
 * `minIntervalMs` (the first notice at once, the rest of a burst once at the end of the
 * interval), never while the browser tab is hidden (once when it is shown again), and once
 * after the stream comes back from a drop. While the stream is not live it falls back to a
 * poll every `fallbackMs` (when given); without one, while the tab's connection is down
 * (`offline`, `stale`, or `paused` when the server would not open it), every
 * `LIVE_FALLBACK_MS`: a page never depends on the push alone, and degrades to timed re-reads
 * without a word of its own (the top bar says once that live updates are paused).
 */
import { useEffect, useRef, useSyncExternalStore } from "react";

import {
  liveStatus,
  onLiveStatus,
  subscribeLive,
  type LiveJobEvent,
  type LiveStatus,
  type LiveTopic,
} from "@/app/data/liveStream";

/** The timed re-read of a page that gave no `fallbackMs`, while its live connection is down. */
export const LIVE_FALLBACK_MS = 60_000;
const DEGRADED = new Set(["offline", "stale", "paused"]);

export function useLiveStatus(): LiveStatus {
  return useSyncExternalStore(onLiveStatus, liveStatus, liveStatus);
}

export interface LiveTopicsOptions {
  /** The shortest time between two re-reads (default 2 s). */
  minIntervalMs?: number;
  /** Poll at this interval while the stream is not live (default: no poll). */
  fallbackMs?: number;
  /** Subscribe only while true (default true). */
  enabled?: boolean;
}

/** A leading-and-trailing throttle: `fire` at once, then at most once per `minMs`. */
export function createThrottle(
  fire: () => void,
  minMs: number,
  clock: () => number = () => Date.now(),
  timers: { set: (fn: () => void, ms: number) => unknown; clear: (handle: unknown) => void } = {
    set: (fn, ms) => setTimeout(fn, ms),
    clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  },
) {
  let last = -Infinity;
  let pending: unknown = null;
  const run = () => {
    pending = null;
    last = clock();
    fire();
  };
  return {
    call() {
      if (pending !== null) return;
      const wait = last + minMs - clock();
      if (wait <= 0) run();
      else pending = timers.set(run, wait);
    },
    cancel() {
      if (pending !== null) timers.clear(pending);
      pending = null;
    },
  };
}

export function useLiveTopics(
  topics: readonly Exclude<LiveTopic, "jobs">[],
  reload: () => void,
  { minIntervalMs = 2_000, fallbackMs, enabled = true }: LiveTopicsOptions = {},
): void {
  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  const key = [...topics].sort().join(",");
  useEffect(() => {
    if (!enabled || !key) return undefined;
    let dirty = false;
    const throttle = createThrottle(() => {
      if (document.visibilityState !== "visible") {
        dirty = true;
        return;
      }
      reloadRef.current();
    }, minIntervalMs);
    const stops = key.split(",").map((topic) => subscribeLive(topic as Exclude<LiveTopic, "jobs">, () => throttle.call()));
    let wasLive = liveStatus().state === "live";
    let pollEvery = 0;
    let poll: ReturnType<typeof setInterval> | undefined;
    const setPoll = (status: LiveStatus) => {
      const every = status.state === "live" ? 0 : fallbackMs ?? (DEGRADED.has(status.state) ? LIVE_FALLBACK_MS : 0);
      if (every === pollEvery) return;
      if (poll) clearInterval(poll);
      poll = undefined;
      pollEvery = every;
      if (every) poll = setInterval(() => throttle.call(), every);
    };
    setPoll(liveStatus());
    const stopStatus = onLiveStatus((status) => {
      setPoll(status);
      const live = status.state === "live";
      if (live === wasLive) return;
      // Back from a drop: whatever changed meanwhile (the server resumes too; this is cheap).
      if (live) throttle.call();
      wasLive = live;
    });
    const shown = () => {
      if (document.visibilityState === "visible" && dirty) {
        dirty = false;
        throttle.call();
      }
    };
    document.addEventListener("visibilitychange", shown);
    return () => {
      for (const stop of stops) stop();
      stopStatus();
      throttle.cancel();
      if (poll) clearInterval(poll);
      document.removeEventListener("visibilitychange", shown);
    };
  }, [enabled, fallbackMs, key, minIntervalMs]);
}

/**
 * The caller's own jobs as they move (`jobs` events: id, kind, status, progress 0-1, step).
 * The first events after a connection are every job still running, so a page opened mid-run
 * shows it at once.
 */
export function useLiveJobs(onJob: (job: LiveJobEvent) => void, enabled = true): void {
  const ref = useRef(onJob);
  ref.current = onJob;
  useEffect(() => {
    if (!enabled) return undefined;
    return subscribeLive("jobs", (job) => ref.current(job));
  }, [enabled]);
}
