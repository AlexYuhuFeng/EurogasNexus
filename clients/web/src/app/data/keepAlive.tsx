/**
 * Keep a heavy page alive while the user is elsewhere: hidden, not unmounted.
 *
 * A page like Desk → Network builds a WebGL map, its sources and layers, its selection and
 * camera. Unmounting it when the user opens another mode and rebuilding it on return cost a
 * second or more and every read again. Here the page is rendered once, at the shell, into a
 * host element that the page's slot shows while the page is open and that is parked (hidden)
 * otherwise, so returning is instant and finds everything as it was.
 *
 * - `<KeptSlot id>`: where the page shows. Mounting it shows the page (and marks it visited).
 * - `<Kept id>{(active) => page}</Kept>`: rendered once at the shell; renders nothing until the
 *   slot was first shown, then keeps the page mounted. `active` says whether it is on screen:
 *   a kept page pauses its timers and rendering while it is not.
 * - Released (unmounted) on a change of signed-in principal or sign-out (`setReadCacheScope`),
 *   and after `KEEP_PARKED_MS` parked: the stand-in for memory pressure, which browsers do not
 *   signal. A released page simply builds again on its next visit.
 *
 * Same rule as the read cache (readCache.ts): show what was there at once, refresh behind it.
 */
import { Fragment, useLayoutEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { onReadCacheScopeChange } from "@/app/data/readCache";

/** How long a parked page is kept before it is released. */
export const KEEP_PARKED_MS = 30 * 60 * 1000;

interface KeptState {
  host: HTMLDivElement;
  visited: boolean;
  active: boolean;
  releaseTimer: ReturnType<typeof setTimeout> | null;
  /** Bumped on a change of principal: the page mounts afresh, nothing of the last one stays. */
  generation: number;
}

const kept = new Map<string, KeptState>();
const listeners = new Set<() => void>();
let parking: HTMLDivElement | null = null;
let version = 0;

function emit(): void {
  version += 1;
  for (const listener of listeners) listener();
}

function parkingLot(): HTMLDivElement {
  if (!parking) {
    parking = document.createElement("div");
    parking.className = "kept-parking";
    parking.setAttribute("aria-hidden", "true");
    parking.style.display = "none";
    document.body.appendChild(parking);
  }
  return parking;
}

function stateFor(id: string): KeptState {
  let state = kept.get(id);
  if (!state) {
    const host = document.createElement("div");
    host.className = "kept-host";
    host.dataset.kept = id;
    // Laid out as if the wrapper were absent.
    host.style.display = "contents";
    parkingLot().appendChild(host);
    state = { host, visited: false, active: false, releaseTimer: null, generation: 0 };
    kept.set(id, state);
  }
  return state;
}

/** Release a kept page (it unmounts; the next visit builds it again). */
export function releaseKept(id?: string): void {
  for (const [key, state] of kept) {
    if (id !== undefined && key !== id) continue;
    if (state.active) continue;
    if (state.releaseTimer) clearTimeout(state.releaseTimer);
    state.releaseTimer = null;
    state.visited = false;
  }
  emit();
}

// A different principal (or none: sign-out) never sees the last one's kept pages: a parked
// page is released, one on screen mounts afresh.
onReadCacheScopeChange((previous) => {
  // Signing in (from no principal) has nothing of anyone's to drop.
  if (previous === "anonymous") return;
  for (const state of kept.values()) {
    state.generation += 1;
    if (!state.active) state.visited = false;
  }
  emit();
});

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Where a kept page shows. Its presence is what makes the page active. */
export function KeptSlot({ id }: { id: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const state = stateFor(id);
    ref.current?.appendChild(state.host);
    if (state.releaseTimer) clearTimeout(state.releaseTimer);
    state.releaseTimer = null;
    state.visited = true;
    state.active = true;
    emit();
    return () => {
      parkingLot().appendChild(state.host);
      state.active = false;
      state.releaseTimer = setTimeout(() => releaseKept(id), KEEP_PARKED_MS);
      emit();
    };
  }, [id]);
  return <div ref={ref} className="kept-slot" data-kept-slot={id} style={{ display: "contents" }} />;
}

/** Whether the kept page `id` is on screen now. */
export function useKeptActive(id: string): boolean {
  useSyncExternalStore(subscribe, () => version, () => 0);
  return kept.get(id)?.active ?? false;
}

/** The kept page, rendered once at the shell into its host (see the module doc). */
export function Kept({ id, children }: { id: string; children: (active: boolean) => ReactNode }) {
  useSyncExternalStore(subscribe, () => version, () => 0);
  const state = typeof document === "undefined" ? null : stateFor(id);
  if (!state || !state.visited) return null;
  return createPortal(<Fragment key={state.generation}>{children(state.active)}</Fragment>, state.host);
}
