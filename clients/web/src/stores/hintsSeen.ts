/**
 * The first-use hints this person has dismissed (`hints_seen`, personal, on the server and
 * mirrored on this device), and whether hints are off on this device (the acceptance sweep sets
 * `egn.hints.off` so a fresh test identity is not met by a hint on every page).
 */
import { create } from "zustand";

import { api } from "../api/client.ts";
import { parseSeen, replayPage, serialiseSeen } from "../components/ui/firstUseHintsModel.ts";

export const HINTS_SEEN_STORAGE_KEY = "egn.hints.seen";
export const HINTS_OFF_STORAGE_KEY = "egn.hints.off";

function read(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private window: the choice holds for this page only.
  }
}

interface HintsSeenState {
  seen: Set<string>;
  off: boolean;
  /** From the server's effective preferences at sign-in. */
  apply: (value: string | null | undefined) => void;
  dismiss: (ids: readonly string[]) => void;
  /** Forget one page's hints ("desk.today"), or every page's with no prefix. */
  replay: (pagePrefix?: string) => void;
}

function persist(seen: Set<string>): void {
  const value = serialiseSeen(seen);
  write(HINTS_SEEN_STORAGE_KEY, value);
  void api.saveMyPreferences({ hints_seen: value || null }).catch(() => undefined);
}

export const useHintsSeenStore = create<HintsSeenState>((set, get) => ({
  seen: parseSeen(read(HINTS_SEEN_STORAGE_KEY)),
  off: read(HINTS_OFF_STORAGE_KEY) === "1",
  apply: (value) => {
    const merged = new Set([...get().seen, ...parseSeen(value)]);
    write(HINTS_SEEN_STORAGE_KEY, serialiseSeen(merged));
    set({ seen: merged });
  },
  dismiss: (ids) => {
    const seen = new Set([...get().seen, ...ids]);
    persist(seen);
    set({ seen });
  },
  replay: (pagePrefix) => {
    const seen = pagePrefix ? replayPage(get().seen, pagePrefix) : new Set<string>();
    persist(seen);
    set({ seen });
  },
}));
