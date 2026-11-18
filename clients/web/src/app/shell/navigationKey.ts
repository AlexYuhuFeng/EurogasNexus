/**
 * Where the reader is (page, task, view), as one value that changes on every navigation. Floating
 * surfaces (Popover, Dialog, Sheet) close when it changes, so a panel opened on one page never
 * floats over the next (docs/product/UX_REFERENCE.md, rule 22). The shell publishes it; the
 * primitives subscribe. A surface that should survive navigation (none today) would opt out.
 */
import { useEffect, useRef } from "react";
import { create } from "zustand";

interface NavigationKeyState {
  key: string;
  setKey: (key: string) => void;
}

export const useNavigationKeyStore = create<NavigationKeyState>((set) => ({
  key: "",
  setKey: (key) => set((state) => (state.key === key ? state : { key })),
}));

/** The part of an address that names a place: page, task, view, panel. */
export function navigationKeyFor(search: string): string {
  const params = new URLSearchParams(search);
  return ["workspace", "task", "view", "panel"].map((name) => params.get(name) ?? "").join("|");
}

/**
 * The rule as a pure step: given where the surface was opened (`openedAt`, null when closed),
 * whether it is open, and the current place, return the new record and whether to close it.
 */
export function navigationStep(
  openedAt: string | null,
  active: boolean,
  key: string,
): { openedAt: string | null; close: boolean } {
  if (!active) return { openedAt: null, close: false };
  if (openedAt === null) return { openedAt: key, close: false };
  if (openedAt !== key) return { openedAt: null, close: true };
  return { openedAt, close: false };
}

/** Call `onNavigate` when the reader moves to another page, task or view while `active`. */
export function useCloseOnNavigation(active: boolean, onNavigate: () => void): void {
  const key = useNavigationKeyStore((state) => state.key);
  const openedAt = useRef<string | null>(null);
  const callback = useRef(onNavigate);
  callback.current = onNavigate;
  useEffect(() => {
    const step = navigationStep(openedAt.current, active, key);
    openedAt.current = step.openedAt;
    if (step.close) callback.current();
  }, [active, key]);
}
