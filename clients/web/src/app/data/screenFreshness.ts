/**
 * The pure rules behind app/data/connection.ts (no imports with effects, so they are tested on
 * their own): when the screen stops being current, how often an unreachable server is asked
 * again, and how this browser's clock is measured against the server's.
 */
import type { LiveStatus } from "./liveStream";

/** The browser's clock may differ from the server's by this much before the desk is told. */
export const CLOCK_SKEW_WARN_MS = 5_000;
/** The live connection may be quiet this long (its own stale rule) before figures are stale. */
export const LIVE_QUIET_STALE_MS = 15_000;
export const PROBE_START_MS = 5_000;
export const PROBE_MAX_MS = 30_000;
export const CLOCK_CHECK_EVERY_MS = 10 * 60_000;

export interface HealthProbeAnswer {
  server_time_utc?: string | null;
  clock?: { state?: string; offset_seconds?: number | null; synchronised?: boolean | null; threshold_seconds?: number } | null;
}

export interface ServerClock {
  state: string;
  offsetSeconds: number | null;
  synchronised: boolean | null;
  thresholdSeconds: number | null;
}

export interface ConnectionState {
  browserOnline: boolean;
  serverReachable: boolean;
  /** When the server last answered (ms epoch), null before the first answer. */
  lastContactAt: number | null;
  /** When it stopped answering, null while it answers. */
  unreachableSince: number | null;
  /** Browser clock minus server clock (ms), null before the first measurement. */
  clockSkewMs: number | null;
  /** The server's own clock check (application/clock_check.py), null before the first read. */
  serverClock: ServerClock | null;
}

export type StaleReason = "browser_offline" | "server_unreachable" | "live_quiet";

export type ScreenFreshness =
  | { current: true }
  | { current: false; reason: StaleReason; since: number | null };

/** Screen freshness from the connection and the live stream, at `at`. Exported for tests. */
export function screenFreshnessOf(connection: ConnectionState, stream: LiveStatus, at: number): ScreenFreshness {
  const since = connection.lastContactAt ?? stream.lastEventAt ?? null;
  if (!connection.browserOnline) return { current: false, reason: "browser_offline", since };
  if (!connection.serverReachable) return { current: false, reason: "server_unreachable", since };
  // A live connection that dropped or went silent: figures stop moving although reads work.
  // A refused stream (`paused`) is not stale: pages re-read on a timer then.
  const quiet = stream.state === "offline" || stream.state === "stale" || (stream.state === "connecting" && stream.lastEventAt !== null);
  if (quiet && stream.lastEventAt !== null && at - stream.lastEventAt > LIVE_QUIET_STALE_MS) {
    return { current: false, reason: "live_quiet", since: stream.lastEventAt };
  }
  return { current: true };
}

/** Browser clock minus server clock (ms) from one answer: the server answered mid-round-trip. */
export function skewMs(serverTimeUtc: string | null | undefined, sent: number, received: number): number | null {
  const serverAt = serverTimeUtc ? Date.parse(serverTimeUtc) : NaN;
  return Number.isFinite(serverAt) ? Math.round((sent + received) / 2 - serverAt) : null;
}

/** The wait before asking an unreachable server again, attempt `n` (1-based): 5 s doubling to 30 s. */
export function probeDelayMs(n: number): number {
  return Math.min(PROBE_MAX_MS, PROBE_START_MS * 2 ** Math.max(0, n - 1));
}

/** Whether the browser's clock disagrees with the server's by more than a few seconds. */
export function clockSkewed(connection: ConnectionState): boolean {
  return connection.clockSkewMs !== null && Math.abs(connection.clockSkewMs) > CLOCK_SKEW_WARN_MS;
}

