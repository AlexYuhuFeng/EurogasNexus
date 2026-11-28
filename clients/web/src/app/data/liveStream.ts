/**
 * The browser tab's ONE live connection (`/api/stream/live`), shared by everything on the page.
 *
 * The server caps how many live streams one person may hold open at once
 * (`EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL`), so a tab holds exactly one, for every topic, and
 * keeps it across page changes: pages, hooks and the store attach listeners to it and detach
 * them, and nothing re-opens the connection when the set of listeners changes. It opens while
 * the session has it turned on and at least one listener is attached (a count of listeners
 * across all topics and events), and closes a short while after the last one detached.
 *
 * What it carries: a `change` notice per topic (`prices`, `trades`, `alerts`, `outages`,
 * `cargoes`, ...) that names a topic and a time, never a row: the page answers it with its own
 * (conditional) read, so a notice never carries data the page would have to entitle; the
 * opportunity engine's `opportunity` and `evaluated` events (`subscribeLiveEvent`); and the
 * caller's `jobs`. Bursts are coalesced twice: the server sends one notice per topic per poll,
 * and `useLiveTopics` (app/hooks/useLive.ts) re-reads at most once per its interval.
 *
 * The connection's state is published, with the time of the last event and of the last change:
 *
 * - `live`: open and heard from within three heartbeats;
 * - `stale`: open but silent past that (or the server said its store is unavailable): the page
 *   keeps what it shows, says how old it is, and the connection is re-opened;
 * - `offline`: dropped, re-opened after a backoff (1 s doubling to 30 s, with jitter), resuming
 *   from the last event id so nothing that changed meanwhile is missed;
 * - `paused`: the server would not open it (the person's streams are at their limit, as with
 *   several tabs or testers on one account, or it answered with an error). Pages fall back to
 *   timed re-reads quietly; the connection is tried again after a long wait (one minute
 *   doubling to five, with jitter), never once per page;
 * - `connecting` and `idle` (nothing attached, or no authenticated session).
 *
 * The store turns it on for an authenticated commercial session and off at every identity
 * change (stores/api.ts); a `revoked` event ends it until then.
 */
import { openEventStream } from "@/api/client";

export type LiveTopic =
  | "prices"
  | "trades"
  | "deals"
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

/** Every topic, in the order the connection asks for them: the tab's one stream carries all. */
export const LIVE_TAB_TOPICS: readonly LiveTopic[] = [
  "alerts",
  "book",
  "capacity",
  "cargoes",
  "deals",
  "flows",
  "jobs",
  "news",
  "nominations",
  "opportunities",
  "outages",
  "prices",
  "slots",
  "sources",
  "tariffs",
  "trades",
];

export type LiveState = "idle" | "connecting" | "live" | "stale" | "offline" | "paused";

export interface LiveStatus {
  state: LiveState;
  /** When anything was last heard on the connection (ms since epoch). */
  lastEventAt: number | null;
  /** When the server last announced a change of a subscribed topic (its `changed_at`, ms). */
  lastChangeAt: number | null;
  /** When the next reconnect is due while offline or paused (ms). */
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

/** The opportunity engine's own events, carried by the same connection (no figures). */
export type LiveEventName = "opportunity" | "evaluated";

type Listener = (payload: LiveChange | LiveJobEvent) => void;
type EventListener = (payload: unknown) => void;
type Opener = typeof openEventStream;

export const LIVE_BACKOFF_START_MS = 1_000;
export const LIVE_BACKOFF_MAX_MS = 30_000;
/** After a refusal (the person's streams at their limit): one minute doubling to five. */
export const LIVE_PAUSED_START_MS = 60_000;
export const LIVE_PAUSED_MAX_MS = 5 * 60_000;
/** The server's heartbeat; silent for three of them is stale. */
export const LIVE_HEARTBEAT_MS = 5_000;
export const LIVE_STALE_AFTER_MS = 3 * LIVE_HEARTBEAT_MS;
/** How long the connection outlives its last listener: a page change re-attaches within it. */
export const LIVE_LINGER_MS = 10_000;

const listeners = new Map<LiveTopic, Set<Listener>>();
const eventListeners = new Map<LiveEventName, Set<EventListener>>();
const statusListeners = new Set<(status: LiveStatus) => void>();
let status: LiveStatus = { state: "idle", lastEventAt: null, lastChangeAt: null, retryAt: null };
let enabled = false;
let handle: { close: () => void } | null = null;
let lastEventId: string | null = null;
let attempt = 0;
let refusals = 0;
let generation = 0;
let retryTimer: ReturnType<typeof setTimeout> | undefined;
let lingerTimer: ReturnType<typeof setTimeout> | undefined;
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

/** How many listeners are attached, across every topic and event: the connection's count. */
export function liveSubscriberCount(): number {
  let count = 0;
  for (const set of listeners.values()) count += set.size;
  for (const set of eventListeners.values()) count += set.size;
  return count;
}

function jittered(base: number, jitter: number): number {
  return Math.round(base * (0.8 + 0.4 * jitter));
}

/** The delay before reconnect attempt `n` (1-based): 1 s doubling to 30 s, ±20 % jitter. */
export function liveBackoffMs(n: number, jitter = random()): number {
  return jittered(Math.min(LIVE_BACKOFF_MAX_MS, LIVE_BACKOFF_START_MS * 2 ** Math.max(0, n - 1)), jitter);
}

/** The delay after refusal `n` (1-based): 1 min doubling to 5 min, ±20 % jitter. */
export function livePausedMs(n: number, jitter = random()): number {
  return jittered(Math.min(LIVE_PAUSED_MAX_MS, LIVE_PAUSED_START_MS * 2 ** Math.max(0, n - 1)), jitter);
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
  if (watchdog) clearInterval(watchdog);
  watchdog = undefined;
}

function wanted(): boolean {
  return enabled && liveSubscriberCount() > 0;
}

function scheduleReconnect(state: "offline" | "stale" | "paused" = "offline") {
  close();
  if (!wanted()) {
    publish({ state: "idle", retryAt: null });
    return;
  }
  let delay: number;
  if (state === "paused") {
    refusals += 1;
    delay = livePausedMs(refusals);
  } else {
    attempt += 1;
    delay = liveBackoffMs(attempt);
  }
  publish({ state, retryAt: now() + delay });
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = setTimeout(() => {
    retryTimer = undefined;
    connect();
  }, delay);
}

function dispatchEvent(name: LiveEventName, payload: unknown) {
  for (const listener of eventListeners.get(name) ?? []) listener(payload);
}

function connect() {
  close();
  if (!wanted()) {
    publish({ state: "idle", retryAt: null });
    return;
  }
  const params = new URLSearchParams({ topics: LIVE_TAB_TOPICS.join(",") });
  // A new EventSource cannot set Last-Event-ID: the server reads it from the query too.
  if (lastEventId) params.set("last_event_id", lastEventId);
  const keep = status.state === "stale" || status.state === "paused";
  publish({ state: keep ? status.state : "connecting", retryAt: null });
  const mine = generation;
  const current = <A extends unknown[]>(handler: (...args: A) => void) => (...args: A) => {
    if (mine === generation) handler(...args);
  };
  handle = opener(
    `/stream/live?${params.toString()}`,
    Object.fromEntries(Object.entries({
      ready: (payload) => {
        attempt = 0;
        refusals = 0;
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
      opportunity: (payload) => {
        publish({ lastEventAt: now() });
        dispatchEvent("opportunity", payload);
      },
      evaluated: (payload) => {
        publish({ lastEventAt: now() });
        dispatchEvent("evaluated", payload);
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
    current((next: "open" | "error" | "refused") => {
      if (next === "refused") scheduleReconnect("paused");
      else if (next === "error") scheduleReconnect();
    }),
  );
  watchdog = setInterval(current(() => {
    const heardAt = status.lastEventAt;
    if (status.state !== "live" || heardAt === null) return;
    // Open but silent: say so, and try a fresh connection (the old one may be half-dead).
    if (now() - heardAt > LIVE_STALE_AFTER_MS) scheduleReconnect("stale");
  }), 1_000);
}

/** A listener came or went: open the connection when it is wanted and not open, or let it go. */
function attachmentsChanged() {
  if (!enabled) return;
  if (liveSubscriberCount() > 0) {
    if (lingerTimer) clearTimeout(lingerTimer);
    lingerTimer = undefined;
    if (!handle && !retryTimer) connect();
    return;
  }
  if (lingerTimer) return;
  lingerTimer = setTimeout(() => {
    lingerTimer = undefined;
    if (liveSubscriberCount() > 0) return;
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = undefined;
    close();
    publish({ state: "idle", retryAt: null });
  }, LIVE_LINGER_MS);
}

/** Listen to one topic's change notices (or, for `jobs`, job events). Returns the unsubscribe. */
export function subscribeLive(topic: "jobs", listener: (job: LiveJobEvent) => void): () => void;
export function subscribeLive(topic: Exclude<LiveTopic, "jobs">, listener: (change: LiveChange) => void): () => void;
export function subscribeLive(topic: LiveTopic, listener: (payload: never) => void): () => void {
  const set = listeners.get(topic) ?? new Set<Listener>();
  set.add(listener as Listener);
  listeners.set(topic, set);
  attachmentsChanged();
  return () => {
    set.delete(listener as Listener);
    attachmentsChanged();
  };
}

/** Listen to the opportunity engine's `opportunity` or `evaluated` events. */
export function subscribeLiveEvent(name: LiveEventName, listener: (payload: unknown) => void): () => void {
  const set = eventListeners.get(name) ?? new Set<EventListener>();
  set.add(listener);
  eventListeners.set(name, set);
  attachmentsChanged();
  return () => {
    set.delete(listener);
    attachmentsChanged();
  };
}

export function liveStatus(): LiveStatus {
  return status;
}

/** Whether changes arrive as they happen; otherwise a page re-reads on its timer. */
export function liveIsUp(): boolean {
  return status.state === "live";
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
  if (lingerTimer) clearTimeout(lingerTimer);
  lingerTimer = undefined;
  attempt = 0;
  refusals = 0;
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
  eventListeners.clear();
  statusListeners.clear();
  opener = options.open ?? openEventStream;
  now = options.clock ?? (() => Date.now());
  random = options.jitter ?? (() => Math.random());
  status = { state: "idle", lastEventAt: null, lastChangeAt: null, retryAt: null };
}
