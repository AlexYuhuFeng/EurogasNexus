/**
 * Can this screen be trusted as current? One answer for the whole client (small-desk plan 3.7).
 *
 * Three things can leave figures on screen that no longer move: the browser is offline, the
 * server does not answer, or the live connection has gone quiet. This store combines them into
 * one `ScreenFreshness`: `current`, or not current with the reason and the time the screen was
 * last known good (`since`). Everything that shows a number reads it through one hook:
 *
 * - `LiveValue` (every live cell of a DataGrid, every live KeyFigure) keeps the last value,
 *   stops flashing and shows a quiet stale mark with the time;
 * - `KeyFigure` with `live` says "stale" and the time beside the value;
 * - the shell sets `data-screen-stale` on the app root, which mutes every tabular figure on
 *   every page (one CSS rule, styles/app.css), so nothing is left looking live;
 * - `ConnectionNotice` says once, calmly, that the server cannot be reached, shows the time of
 *   the last known picture, and tells the desk to rely on the trading screen until it clears.
 *
 * Nothing is blanked: the read cache keeps the last good answer (app/data/readCache.ts).
 *
 * Reachability is learnt from every API answer (api/client.ts reports each one): a network
 * failure, or a 502/504 from the proxy in front of the API, marks the server unreachable; any
 * other answer marks it reachable. While unreachable, `/api/health` is probed (5 s doubling to
 * 30 s) so the notice clears by itself on recovery even on a page that reads nothing. The same
 * probe reads the server's clock (`server_time_utc`) every ten minutes and measures this
 * browser's clock against it, allowing for the round trip.
 *
 * 屏幕数据是否仍为最新：浏览器离线、服务器无响应或实时连接中断时，保留最后数值并标注时间。
 */
import { useSyncExternalStore } from "react";

import { observeServerAnswers, probeHealth } from "@/api/client";
import { liveStatus, onLiveStatus, type LiveStatus } from "./liveStream";
import {
  CLOCK_CHECK_EVERY_MS,
  probeDelayMs,
  screenFreshnessOf,
  skewMs,
  type ConnectionState,
  type HealthProbeAnswer,
  type ScreenFreshness,
} from "./screenFreshness";

export {
  CLOCK_SKEW_WARN_MS,
  clockSkewed,
  screenFreshnessOf,
  type ConnectionState,
  type ScreenFreshness,
  type ServerClock,
  type StaleReason,
} from "./screenFreshness";

type Prober = () => Promise<HealthProbeAnswer>;

let state: ConnectionState = {
  browserOnline: typeof navigator === "undefined" ? true : navigator.onLine !== false,
  serverReachable: true,
  lastContactAt: null,
  unreachableSince: null,
  clockSkewMs: null,
  serverClock: null,
};
let live: LiveStatus = liveStatus();
const listeners = new Set<() => void>();
let prober: Prober | null = probeHealth;
let probeTimer: ReturnType<typeof setTimeout> | undefined;
let probeAttempt = 0;
let probing = false;
let lastClockCheck = 0;
let now = () => Date.now();
let snapshot: ScreenFreshness = { current: true };

function setState(next: Partial<ConnectionState>) {
  const merged = { ...state, ...next };
  const changed = (Object.keys(merged) as (keyof ConnectionState)[]).some((key) => merged[key] !== state[key]);
  if (!changed) return;
  state = merged;
  recompute();
}

function recompute() {
  const next = screenFreshnessOf(state, live, now());
  const same =
    next.current === snapshot.current &&
    (next.current || (!snapshot.current && next.reason === snapshot.reason && next.since === snapshot.since));
  if (!same) snapshot = next;
  for (const listener of listeners) listener();
}

function scheduleProbe(delay: number) {
  if (probeTimer) clearTimeout(probeTimer);
  probeTimer = setTimeout(() => {
    probeTimer = undefined;
    void probe();
  }, delay);
  (probeTimer as { unref?: () => void }).unref?.();
}

/** Ask the server's health once: reachability and its clock. */
export async function probe(): Promise<void> {
  if (!prober || probing) return;
  probing = true;
  const sent = now();
  try {
    const answer = await prober();
    const received = now();
    noteServerAnswer(true);
    noteServerClock(answer, sent, received);
  } catch {
    noteServerAnswer(false);
  } finally {
    probing = false;
  }
}

/** The browser's clock against the server's, from one health answer and its round trip. */
export function noteServerClock(answer: HealthProbeAnswer, sent: number, received: number): void {
  lastClockCheck = received;
  const clock = answer.clock
    ? {
        state: String(answer.clock.state ?? "unknown"),
        offsetSeconds: answer.clock.offset_seconds ?? null,
        synchronised: answer.clock.synchronised ?? null,
        thresholdSeconds: answer.clock.threshold_seconds ?? null,
      }
    : state.serverClock;
  setState({
    serverClock: clock,
    // The server answered somewhere in the round trip: compare with its middle.
    clockSkewMs: skewMs(answer.server_time_utc, sent, received) ?? state.clockSkewMs,
  });
}

/**
 * Every API answer reports here (api/client.ts). `ok` false is a network failure or a 502/504
 * from the proxy in front of the API: the server is not answering.
 */
export function noteServerAnswer(ok: boolean): void {
  const at = now();
  if (ok) {
    probeAttempt = 0;
    if (probeTimer) clearTimeout(probeTimer);
    probeTimer = undefined;
    setState({ serverReachable: true, lastContactAt: at, unreachableSince: null });
    if (prober && at - lastClockCheck > CLOCK_CHECK_EVERY_MS) {
      lastClockCheck = at;
      scheduleProbe(0);
    }
    return;
  }
  setState({ serverReachable: false, unreachableSince: state.unreachableSince ?? at });
  probeAttempt += 1;
  scheduleProbe(probeDelayMs(probeAttempt));
}

/** The client registers how to ask `/api/health` (no import cycle with api/client.ts). */
export function setHealthProber(next: Prober | null): void {
  prober = next;
}

export function connectionState(): ConnectionState {
  return state;
}

export function screenFreshness(): ScreenFreshness {
  return snapshot;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useConnection(): ConnectionState {
  return useSyncExternalStore(subscribe, connectionState, connectionState);
}

/** The one question every figure asks: is the screen current, and if not since when and why. */
export function useScreenFreshness(): ScreenFreshness {
  return useSyncExternalStore(subscribe, screenFreshness, screenFreshness);
}

const tickListeners = new Set<() => void>();
let tickTimer: ReturnType<typeof setInterval> | undefined;

function subscribeTick(listener: () => void): () => void {
  tickListeners.add(listener);
  if (!tickTimer && typeof window !== "undefined") {
    tickTimer = setInterval(() => {
      for (const each of tickListeners) each();
    }, 1_000);
  }
  return () => {
    tickListeners.delete(listener);
    if (!tickListeners.size && tickTimer) {
      clearInterval(tickTimer);
      tickTimer = undefined;
    }
  };
}

/**
 * The time now, moving in steps of `stepMs`, from one timer per tab. A figure judged by its age
 * (a quote older than its source's cadence) must be judged again as time passes, not only when
 * a new answer arrives: a feed that stopped sends nothing that would re-render it.
 */
export function useNow(stepMs = 5_000): number {
  return useSyncExternalStore(
    subscribeTick,
    () => Math.floor(Date.now() / stepMs) * stepMs,
    () => Math.floor(Date.now() / stepMs) * stepMs,
  );
}

let started = false;

/** Listen to the browser's online state, the live stream and time passing (once per tab). */
export function startConnectionWatch(): void {
  if (started || typeof window === "undefined") return;
  started = true;
  observeServerAnswers(noteServerAnswer);
  window.addEventListener("online", () => {
    setState({ browserOnline: true });
    void probe();
  });
  window.addEventListener("offline", () => setState({ browserOnline: false }));
  onLiveStatus((next) => {
    const dropped = next.state === "offline" && live.state !== "offline";
    live = next;
    recompute();
    // A dropped stream is the first sign of a server gone away: ask its health now.
    if (dropped) void probe();
  });
  // The live rule depends on time passing, not only on events.
  setInterval(recompute, 1_000);
  if (prober) void probe();
}

/** Tests: start from nothing with a fake clock. */
export function resetConnectionForTests(options: { clock?: () => number; prober?: Prober | null } = {}): void {
  if (probeTimer) clearTimeout(probeTimer);
  probeTimer = undefined;
  probeAttempt = 0;
  probing = false;
  lastClockCheck = 0;
  now = options.clock ?? (() => Date.now());
  prober = options.prober ?? null;
  live = liveStatus();
  state = { browserOnline: true, serverReachable: true, lastContactAt: null, unreachableSince: null, clockSkewMs: null, serverClock: null };
  snapshot = { current: true };
  listeners.clear();
}
