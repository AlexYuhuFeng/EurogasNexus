/**
 * The session's live stream (`/api/stream/live`): one connection, per-topic subscriptions.
 *
 * A page subscribes to the topics it shows (`prices`, `trades`, `alerts`, ...); the connection
 * asks the server for the union of what is subscribed and is re-opened, resuming from the last
 * event id, when that set changes. A notice names a topic and a time, never a row: the page
 * answers it with its own (conditional) read, so a notice never carries data the page would
 * have to entitle. Bursts are coalesced twice: the server sends one notice per topic per poll,
 * and `useLiveTopics` (app/hooks/useLive.ts) re-reads at most once per its interval.
 *
 * The connection's state is published, with the time of the last event and of the last change:
 *
 * - `live`: open and heard from within three heartbeats;
 * - `stale`: open but silent past that (or the server said its store is unavailable): the page
 *   keeps what it shows, says how old it is, and the connection is re-opened;
 * - `offline`: closed by an error, re-opened after a backoff (1 s doubling to 30 s, with
 *   jitter), resuming from the last event id so nothing that changed meanwhile is missed;
 * - `connecting` and `idle` (nothing subscribed, or no authenticated session).
 *
 * The store turns it on for an authenticated commercial session and off at every identity
 * change (stores/api.ts, beside the decision streams); a `revoked` event ends it until then.
 */
import { openEventStream } from "@/api/client";

export type LiveTopic =
  | "prices"
  | "trades"
  | "alerts"
  | "nominations"
  | "tariffs"
  | "outages"
  | "flows"
  | "cargoes"
  | "slots"
  | "opportunities"
  | "book"
  | "capacity"
  | "sources"
  | "news"
  | "jobs";

export type LiveState = "idle" | "connecting" | "live" | "stale" | "offline";

export interface LiveStatus {
  state: LiveState;
  /** When anything was last heard on the connection (ms since epoch). */
  lastEventAt: number | null;
  /** When the server last announced a change of a subscribed topic (its `changed_at`, ms). */
  lastChangeAt: number | null;
  /** When the next reconnect is due while offline (ms). */
  retryAt: number | null;
}

/** One of the caller's jobs as the stream sends it (`jobs` event). */
export interface LiveJobEvent {
  job_id: string;
  kind: string;
  status: string;
  /** 0 to 1. */
  progress: number;
  /** The current step's label, when the job records one. */
  step: string | null;
  error_code: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface LiveChange {
  topic: LiveTopic;
  changed_at: string;
}

type Listener = (payload: LiveChange | LiveJobEvent) => void;
type Opener = typeof openEventStream;

export const LIVE_BACKOFF_START_MS = 1_000;
export const LIVE_BACKOFF_MAX_MS = 30_000;
/** The server's heartbeat; silent for three of them is stale. */
export const LIVE_HEARTBEAT_MS = 5_000;
export const LIVE_STALE_AFTER_MS = 3 * LIVE_HEARTBEAT_MS;
const RESUBSCRIBE_DEBOUNCE_MS = 50;

const listeners = new Map<LiveTopic, Set<Listener>>();
const statusListeners = new Set<(status: LiveStatus) => void>();
let status: LiveStatus = { state: "idle", lastEventAt: null, lastChangeAt: null, retryAt: null };
let enabled = false;
let handle: { close: () => void } | null = null;
let openTopics = "";
let lastEventId: string | null = null;
let attempt = 0;
let generation = 0;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let resubscribeTimer: ReturnType<typeof setTimeout> | undefined;
let watchdog: ReturnType<typeof setInterval> | undefined;
let opener: Opener = openEventStream;
let now = () => Date.now();
let random = () => Math.random();

function publish(next: Partial<LiveStatus>) {
  const merged = { ...status, ...next };
  if (
    merged.state === status.state &&
    merged.lastEventAt === status.lastEventAt &&
    merged.lastChangeAt === status.lastChangeAt &&
    merged.retryAt === status.retryAt
  ) {
    return;
  }
  status = merged;
  for (const listener of statusListeners) listener(status);
}

function wantedTopics(): string {
  return [...listeners.entries()]
    .filter(([, set]) => set.size > 0)
    .map(([topic]) => topic)
    .sort()
    .join(",");
}

/** The delay before reconnect attempt `n` (1-based): 1 s doubling to 30 s, ±20 % jitter. */
export function liveBackoffMs(n: number, jitter = random()): number {
  const base = Math.min(LIVE_BACKOFF_MAX_MS, LIVE_BACKOFF_START_MS * 2 ** Math.max(0, n - 1));
  return Math.round(base * (0.8 + 0.4 * jitter));
}

function remember(payload: unknown) {
  publish({ lastEventAt: now() });
  const id = payload && typeof payload === "object" ? (payload as { event_id?: unknown }).event_id : null;
  if (typeof id === "string" && id) lastEventId = id;
}

function close() {
  generation += 1;
  handle?.close();
  handle = null;
  openTopics = "";
  if (watchdog) clearInterval(watchdog);
  watchdog = undefined;
}

function scheduleReconnect(state: "offline" | "stale" = "offline") {
  close();
  if (!enabled || !wantedTopics()) return;
  attempt += 1;
  const delay = liveBackoffMs(attempt);
  publish({ state, retryAt: now() + delay });
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = setTimeout(() => {
    retryTimer = undefined;
    connect();
  }, delay);
}

function connect() {
  const topics = wantedTopics();
  close();
  if (!enabled || !topics) {
    publish({ state: "idle", retryAt: null });
    return;
  }
  const params = new URLSearchParams({ topics });
  // A new EventSource cannot set Last-Event-ID: the server reads it from the query too.
  if (lastEventId) params.set("last_event_id", lastEventId);
  publish({ state: status.state === "stale" ? "stale" : "connecting", retryAt: null });
  openTopics = topics;
  const mine = generation;
  const current = <A extends unknown[]>(handler: (...args: A) => void) => (...args: A) => {
    if (mine === generation) handler(...args);
  };
  handle = opener(
    `/stream/live?${params.toString()}`,
    Object.fromEntries(Object.entries({
      ready: (payload) => {
        attempt = 0;
        remember(payload);
        publish({ state: "live", retryAt: null });
      },
      change: (payload) => {
        remember(payload);
        const change = payload as LiveChange;
        if (!change || typeof change.topic !== "string") return;
        const at = Date.parse(change.changed_at);
        if (Number.isFinite(at)) publish({ lastChangeAt: Math.max(status.lastChangeAt ?? 0, at) });
        if (status.state !== "live") publish({ state: "live" });
        for (const listener of listeners.get(change.topic) ?? []) listener(change);
      },
      jobs: (payload) => {
        remember(payload);
        const job = payload as LiveJobEvent;
        if (!job || typeof job.job_id !== "string") return;
        for (const listener of listeners.get("jobs") ?? []) listener(job);
      },
      heartbeat: (payload) => {
        remember(payload);
        if (status.state === "stale") publish({ state: "live" });
      },
      warning: () => publish({ state: "stale", lastEventAt: now() }),
      revoked: () => {
        enabled = false;
        close();
        publish({ state: "idle", retryAt: null });
      },
    } as Record<string, (payload: unknown) => void>).map(([name, handler]) => [name, current(handler)])),
    current((next: "open" | "error") => {
      if (next === "error") scheduleReconnect();
    }),
  );
  watchdog = setInterval(current(() => {
    const heard = status.lastEventAt;
    if (status.state !== "live" || heard === null) return;
    // Open but silent: say so, and try a fresh connection (the old one may be half-dead).
    if (now() - heard > LIVE_STALE_AFTER_MS) scheduleReconnect("stale");
  }), 1_000);
}

function resubscribe() {
  if (resubscribeTimer) clearTimeout(resubscribeTimer);
  resubscribeTimer = setTimeout(() => {
    resubscribeTimer = undefined;
    if (!enabled) return;
    const topics = wantedTopics();
    if (topics === openTopics && handle) return;
    if (retryTimer) return; // a reconnect is due and will ask for the new set
    connect();
  }, RESUBSCRIBE_DEBOUNCE_MS);
}

/** Listen to one topic's change notices (or, for `jobs`, job events). Returns the unsubscribe. */
export function subscribeLive(topic: "jobs", listener: (job: LiveJobEvent) => void): () => void;
export function subscribeLive(topic: Exclude<LiveTopic, "jobs">, listener: (change: LiveChange) => void): () => void;
export function subscribeLive(topic: LiveTopic, listener: (payload: never) => void): () => void {
  const set = listeners.get(topic) ?? new Set<Listener>();
  set.add(listener as Listener);
  listeners.set(topic, set);
  resubscribe();
  return () => {
    set.delete(listener as Listener);
    resubscribe();
  };
}

export function liveStatus(): LiveStatus {
  return status;
}

export function onLiveStatus(listener: (status: LiveStatus) => void): () => void {
  statusListeners.add(listener);
  return () => {
    statusListeners.delete(listener);
  };
}

/** Turned on for an authenticated commercial session, off at every identity change. */
export function setLiveEnabled(next: boolean): void {
  if (next === enabled) return;
  enabled = next;
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = undefined;
  attempt = 0;
  if (!next) {
    // Another identity must not resume this one's position.
    lastEventId = null;
    close();
    publish({ state: "idle", retryAt: null, lastEventAt: null, lastChangeAt: null });
    return;
  }
  connect();
}

/** Tests: replace the transport and the clocks, and start from nothing. */
export function resetLiveStreamForTests(options: { open?: Opener; clock?: () => number; jitter?: () => number } = {}): void {
  setLiveEnabled(false);
  listeners.clear();
  statusListeners.clear();
  if (resubscribeTimer) clearTimeout(resubscribeTimer);
  resubscribeTimer = undefined;
  opener = options.open ?? openEventStream;
  now = options.clock ?? (() => Date.now());
  random = options.jitter ?? (() => Math.random());
  status = { state: "idle", lastEventAt: null, lastChangeAt: null, retryAt: null };
}
