/**
 * Which answers on screen are a server's kept result that is being recomputed (`meta.view`,
 * application/warm_views.py), and since when.
 *
 * A heavy read answers at once from the last result the server computed for this caller. When
 * data behind it has changed since, the answer says `state: "refreshing"` with its
 * `computed_at_utc`: the page shows it, and the top bar says the figures are from that time and
 * being updated, so a kept result is never presented as newer than it is. A later fresh answer of
 * the same read clears it; so does `REFRESHING_SHOWN_MS` passing (the server's refresh is done by
 * then, and the page's next read gets it).
 */
import { useSyncExternalStore } from "react";

export interface ViewMetaDTO {
  state: "fresh" | "refreshing";
  computed_at_utc: string;
  max_age_seconds: number;
}

export const REFRESHING_SHOWN_MS = 20_000;

const refreshing = new Map<string, { computedAt: string; until: number }>();
const listeners = new Set<() => void>();
let snapshot: string | null = null;

function publish(now: number): void {
  for (const [path, entry] of refreshing) if (entry.until <= now) refreshing.delete(path);
  let oldest: string | null = null;
  for (const { computedAt } of refreshing.values()) if (oldest === null || computedAt < oldest) oldest = computedAt;
  if (oldest !== snapshot) {
    snapshot = oldest;
    for (const listener of listeners) listener();
  }
}

/** Record what one read's answer said about itself (called for every GET). */
export function noteViewMeta(path: string, meta: unknown, now = Date.now()): void {
  const view = (meta as { view?: ViewMetaDTO } | null | undefined)?.view;
  if (view?.state === "refreshing" && typeof view.computed_at_utc === "string") {
    refreshing.set(path, { computedAt: view.computed_at_utc, until: now + REFRESHING_SHOWN_MS });
    const timer = setTimeout(() => publish(Date.now()), REFRESHING_SHOWN_MS + 50);
    // Under Node (tests) the lapse timer must not keep the process alive.
    (timer as { unref?: () => void }).unref?.();
  } else if (refreshing.has(path)) {
    refreshing.delete(path);
  }
  publish(now);
}

/** The oldest computed time among answers being refreshed, or null when none is. */
export function refreshingSince(): string | null {
  return snapshot;
}

export function clearViewFreshness(): void {
  refreshing.clear();
  publish(Date.now());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useRefreshingSince(): string | null {
  return useSyncExternalStore(subscribe, refreshingSince, () => null);
}
