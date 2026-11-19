/**
 * The client's read cache: show what was read last, refresh behind it (stale-while-revalidate).
 *
 * Switching tasks or pages used to unmount a panel and blank it until its read answered again. A
 * panel that reads through `useCachedRead` shows its last answer at once, refreshes in the
 * background (`updating`), keeps that last answer if the refresh fails (`error` says so), and only
 * shows a loading state the first time. The data carries its own as-of (every payload does), so a
 * kept answer is never presented as newer than it is.
 *
 * - Keyed by the caller's key (endpoint + parameters) within the signed-in principal: a change of
 *   identity empties the cache (`setReadCacheScope`), sign-out too.
 * - Any write (POST/PUT/PATCH/DELETE through the API client) marks every entry stale
 *   (`invalidateReads`), so the next view reads again after a change.
 * - At most `MAX_ENTRIES` answers are kept, least recently used dropped first.
 *
 * No dependency: a Map, listeners and `useSyncExternalStore`.
 */
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

export const DEFAULT_FRESH_MS = 15_000;
export const MAX_ENTRIES = 120;

export interface ReadSnapshot<T> {
  data: T | undefined;
  error: unknown;
  /** No answer yet: the first read is running. */
  loading: boolean;
  /** An answer is shown and a newer one is being read. */
  updating: boolean;
  /** When the shown answer arrived (ms epoch), 0 when none. */
  at: number;
}

interface Entry {
  snapshot: ReadSnapshot<unknown>;
  stale: boolean;
  inFlight: Promise<void> | null;
  generation: number;
}

const EMPTY: ReadSnapshot<unknown> = { data: undefined, error: null, loading: false, updating: false, at: 0 };
const entries = new Map<string, Entry>();
const listeners = new Map<string, Set<() => void>>();
let scope = "anonymous";

function scoped(key: string): string {
  return `${scope}|${key}`;
}

function emit(fullKey: string): void {
  for (const listener of listeners.get(fullKey) ?? []) listener();
}

function touch(fullKey: string, entry: Entry): void {
  entries.delete(fullKey);
  entries.set(fullKey, entry);
  while (entries.size > MAX_ENTRIES) {
    const oldest = entries.keys().next().value as string;
    entries.delete(oldest);
  }
}

const scopeListeners = new Set<(previous: string, next: string) => void>();

/**
 * Called when the signed-in principal changes (or signs out): what else is kept for the last
 * one goes too (a kept page, app/data/keepAlive.tsx).
 */
export function onReadCacheScopeChange(listener: (previous: string, next: string) => void): () => void {
  scopeListeners.add(listener);
  return () => {
    scopeListeners.delete(listener);
  };
}

/** The signed-in principal: a different one starts from an empty cache. */
export function setReadCacheScope(principalId: string | null | undefined): void {
  const next = principalId ?? "anonymous";
  if (next === scope) return;
  const previous = scope;
  scope = next;
  queueMicrotask(() => {
    for (const listener of scopeListeners) listener(previous, next);
  });
  const keys = [...entries.keys()];
  entries.clear();
  // Called from the shell's render (so no child reads under the old identity): tell subscribers
  // after the render, not during it.
  queueMicrotask(() => {
    for (const key of keys) emit(key);
  });
}

/** Mark every kept answer stale (after a write): the next view reads again, showing it meanwhile. */
export function invalidateReads(): void {
  for (const entry of entries.values()) entry.stale = true;
}

function sameAnswer(shown: unknown, next: unknown): boolean {
  if (shown === next) return true;
  try {
    return JSON.stringify(shown) === JSON.stringify(next);
  } catch {
    return false;
  }
}

/** A stable key from an endpoint and its parameters. */
export function readKey(path: string, params: Record<string, unknown> = {}): string {
  const ordered = Object.keys(params)
    .sort()
    .filter((name) => params[name] !== undefined && params[name] !== null && params[name] !== "")
    .map((name) => `${name}=${String(params[name])}`);
  return ordered.length ? `${path}?${ordered.join("&")}` : path;
}

/** Read `key` unless a fresh answer or a read in flight already covers it. */
export function loadRead<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
  { freshMs = DEFAULT_FRESH_MS, force = false, now = Date.now() }: { freshMs?: number; force?: boolean; now?: number } = {},
): Promise<void> {
  const fullKey = scoped(key);
  const entry = entries.get(fullKey) ?? { snapshot: EMPTY, stale: true, inFlight: null, generation: 0 };
  touch(fullKey, entry);
  if (entry.inFlight && !force) return entry.inFlight;
  const fresh = entry.snapshot.at > 0 && !entry.stale && now - entry.snapshot.at < freshMs;
  if (fresh && !force) return Promise.resolve();
  const mine = ++entry.generation;
  const controller = new AbortController();
  const hasData = entry.snapshot.data !== undefined;
  entry.snapshot = { ...entry.snapshot, loading: !hasData, updating: hasData };
  emit(fullKey);
  const request = fetcher(controller.signal)
    .then((data) => {
      if (entry.generation !== mine) return;
      // An answer equal to the one shown (a revalidation that found nothing new, often a 304)
      // keeps the shown object: nothing downstream re-renders or redraws for it.
      const same = entry.snapshot.data !== undefined && sameAnswer(entry.snapshot.data, data);
      entry.snapshot = { data: same ? entry.snapshot.data : data, error: null, loading: false, updating: false, at: Date.now() };
      entry.stale = false;
    })
    .catch((error: unknown) => {
      if (entry.generation !== mine) return;
      // The last good answer stays; the failure is reported beside it.
      entry.snapshot = { ...entry.snapshot, error, loading: false, updating: false };
    })
    .finally(() => {
      if (entry.generation === mine) entry.inFlight = null;
      emit(fullKey);
    });
  entry.inFlight = request;
  return request;
}

/** The current snapshot for `key` (tests, non-React callers). */
export function peekRead<T>(key: string): ReadSnapshot<T> {
  return (entries.get(scoped(key))?.snapshot ?? EMPTY) as ReadSnapshot<T>;
}

/** Forget everything (sign-out, tests). */
export function clearReadCache(): void {
  const keys = [...entries.keys()];
  entries.clear();
  for (const key of keys) emit(key);
}

/**
 * A panel's read: the last answer at once, a fresh one behind it. `key` null means "nothing to
 * read yet" (a selection not made).
 */
export function useCachedRead<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  { freshMs = DEFAULT_FRESH_MS }: { freshMs?: number } = {},
): ReadSnapshot<T> & { refresh: () => void } {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const fullKey = key === null ? null : scoped(key);
  const subscribe = useCallback(
    (listener: () => void) => {
      if (!fullKey) return () => undefined;
      const set = listeners.get(fullKey) ?? new Set();
      set.add(listener);
      listeners.set(fullKey, set);
      return () => {
        set.delete(listener);
      };
    },
    [fullKey],
  );
  const snapshot = useSyncExternalStore(
    subscribe,
    () => (fullKey ? entries.get(fullKey)?.snapshot ?? EMPTY : EMPTY),
    () => EMPTY,
  ) as ReadSnapshot<T>;
  useEffect(() => {
    if (key === null) return;
    void loadRead(key, (signal) => fetcherRef.current(signal), { freshMs });
  }, [key, freshMs]);
  const refresh = useCallback(() => {
    if (key !== null) void loadRead(key, (signal) => fetcherRef.current(signal), { force: true });
  }, [key]);
  return { ...snapshot, refresh };
}
