/**
 * The Today read (`GET /api/desk/today`, UX-05): one request for the whole first screen.
 *
 * Several surfaces read it: the Today screen, the Portfolio desk, the context strip (which says
 * "Demo data" once on the demo desk) and the top bar's status panel (which names the figures
 * that are not current). They share one cache entry keyed by caller and gas day, so a page
 * makes one request per navigation however many components read it, and React's development
 * double effects (StrictMode) join the request already in flight instead of sending another.
 *
 * The key carries the caller's principal, so a change of identity never shows another caller's
 * figures; `clearDeskTodayCache` drops everything on sign-out.
 */
import { useCallback, useEffect, useSyncExternalStore } from "react";

import { api, type DeskTodayDTO } from "@/api/client";
import { useApiStore } from "@/stores/api";

export interface DeskTodayRead {
  today: DeskTodayDTO | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

interface Snapshot {
  today: DeskTodayDTO | null;
  loading: boolean;
  error: string | null;
}

interface Entry {
  snapshot: Snapshot;
  fetchedAt: number;
  inFlight: Promise<void> | null;
  generation: number;
}

/** A read younger than this is the same navigation's read: reuse it. */
export const DESK_TODAY_REUSE_MS = 5_000;

const EMPTY: Snapshot = { today: null, loading: false, error: null };
const entries = new Map<string, Entry>();
const listeners = new Set<() => void>();
let fetcher: () => Promise<{ data: DeskTodayDTO }> = () => api.deskToday();

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** The cache key: who is asking and for which gas day (the server's day boundary is UTC 05:00/06:00; the UTC date is close enough to tell two days apart). */
export function deskTodayKey(principalId: string | null | undefined, now = Date.now()): string {
  return `${principalId ?? "anonymous"}|${new Date(now).toISOString().slice(0, 10)}`;
}

/** Start a read for `key` unless one is in flight or a recent one can be reused. */
export function loadDeskToday(key: string, force = false, now = Date.now()): Promise<void> {
  const entry = entries.get(key) ?? { snapshot: EMPTY, fetchedAt: 0, inFlight: null, generation: 0 };
  entries.set(key, entry);
  if (entry.inFlight && !force) return entry.inFlight;
  if (!force && entry.snapshot.today && now - entry.fetchedAt < DESK_TODAY_REUSE_MS) return Promise.resolve();
  const mine = ++entry.generation;
  entry.snapshot = { ...entry.snapshot, loading: true };
  emit();
  const request = fetcher()
    .then((response) => {
      if (mine !== entry.generation) return;
      entry.snapshot = { today: response.data, loading: false, error: null };
      entry.fetchedAt = Date.now();
    })
    .catch((caught: unknown) => {
      if (mine !== entry.generation) return;
      entry.snapshot = { ...entry.snapshot, loading: false, error: caught instanceof Error ? caught.message : String(caught) };
    })
    .finally(() => {
      if (entry.inFlight === request) entry.inFlight = null;
      emit();
    });
  entry.inFlight = request;
  return request;
}

/** The cached read for `key` (no request). */
export function deskTodaySnapshot(key: string): Snapshot {
  return entries.get(key)?.snapshot ?? EMPTY;
}

/** Drop every cached read (sign-out, identity change). */
export function clearDeskTodayCache() {
  entries.clear();
  emit();
}

/** Tests replace the request. */
export function setDeskTodayFetcher(next: () => Promise<{ data: DeskTodayDTO }>) {
  fetcher = next;
}

// A change of identity (sign-out, another sign-in) drops every cached read at once.
useApiStore.subscribe((state, previous) => {
  if (state.currentUser?.principal_id !== previous.currentUser?.principal_id) clearDeskTodayCache();
});

function useKey() {
  const principalId = useApiStore((state) => state.currentUser?.principal_id ?? null);
  return deskTodayKey(principalId);
}

/**
 * Read Today. `enabled` false subscribes to whatever is cached without asking the server
 * (the top bar: it shows the stale list when a page has read Today, and never adds a request).
 */
export function useDeskToday(enabled = true): DeskTodayRead {
  const key = useKey();
  const snapshot = useSyncExternalStore(subscribe, () => deskTodaySnapshot(key), () => EMPTY);
  useEffect(() => {
    if (enabled) void loadDeskToday(key);
  }, [enabled, key]);
  const refresh = useCallback(() => {
    void loadDeskToday(key, true);
  }, [key]);
  return { ...snapshot, loading: enabled ? snapshot.loading || (!snapshot.today && !snapshot.error) : snapshot.loading, refresh };
}
