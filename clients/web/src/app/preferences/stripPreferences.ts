/**
 * The situational strip's personal preferences (role-first redesign §5, WP-06).
 *
 * Thresholds, focus hubs and the quiet line are three-tier settings like the language: the
 * person's choice, else the organisation default, else the built-in default
 * (`domain/settings/preferences.py`). The hide list is the person's own and never a default.
 * Everything is presentation: it changes which items qualify for this person's strip, never
 * what they may read.
 */
import { useSyncExternalStore } from "react";

import type { PreferencesDTO } from "../../api/client.ts";
import { canonicalHub } from "../hubAliases.ts";
import { DEFAULT_STRIP_THRESHOLDS, type StripThresholds } from "../model/tickerItems.ts";

/** Mirrors the vocabularies in `domain/settings/preferences.py`. */
export const STRIP_CHOICES = {
  strip_outage_gwh_d: ["25", "50", "100", "200", "500"],
  strip_outage_share_pct: ["25", "50", "75"],
  strip_price_move_pct: ["2", "3", "5", "10"],
  strip_quiet_line: ["on", "off"],
} as const;
export type StripChoiceKey = keyof typeof STRIP_CHOICES;
export const STRIP_CHOICE_KEYS = Object.keys(STRIP_CHOICES) as StripChoiceKey[];

/** Built-in defaults (the server's `BUILT_IN_DEFAULTS`). */
export const STRIP_BUILT_IN: Record<StripChoiceKey | "strip_focus_hubs", string> = {
  strip_outage_gwh_d: "50",
  strip_outage_share_pct: "50",
  strip_price_move_pct: "5",
  strip_quiet_line: "on",
  strip_focus_hubs: "",
};

export const FOCUS_HUB_CHOICES = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF"] as const;
export const MAX_FOCUS_HUBS = 6;
export const MAX_HIDDEN_ITEMS = 40;
/** The server's pattern for one hide entry (`id@signature`). */
const HIDE_ENTRY = /^[a-z_]{2,16}:[A-Za-z0-9:._-]{1,120}@[A-Za-z0-9:._|+-]{0,80}$/;

type Effective = Partial<Record<string, string>>;

function number(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

/** The thresholds a person's effective preferences give (older servers: the defaults). */
export function stripThresholdsFrom(effective: Effective | null | undefined): StripThresholds {
  const values = effective ?? {};
  const hubs = String(values.strip_focus_hubs ?? "")
    .split(",")
    // A preference saved under a hub's other name (GTF) is that hub (ETF).
    .map((hub) => canonicalHub(hub))
    .filter((hub) => (FOCUS_HUB_CHOICES as readonly string[]).includes(hub));
  return {
    outageGwhD: number(values.strip_outage_gwh_d, DEFAULT_STRIP_THRESHOLDS.outageGwhD),
    outageSharePct: number(values.strip_outage_share_pct, DEFAULT_STRIP_THRESHOLDS.outageSharePct),
    priceMovePct: number(values.strip_price_move_pct, DEFAULT_STRIP_THRESHOLDS.priceMovePct),
    focusHubs: [...new Set(hubs)].slice(0, MAX_FOCUS_HUBS),
    showQuietLine: values.strip_quiet_line !== "off",
  };
}

export function hiddenFrom(effective: Effective | null | undefined): string[] {
  return String(effective?.strip_hidden ?? "")
    .split("\n")
    .filter((entry) => HIDE_ENTRY.test(entry));
}

/** The stored form of a hide list: valid entries only, newest kept when it is full. */
export function serializeHidden(entries: readonly string[]): string {
  const valid = [...new Set(entries.filter((entry) => HIDE_ENTRY.test(entry)))];
  return valid.slice(-MAX_HIDDEN_ITEMS).join("\n");
}

/* ------------------------------------------------------------------ the shared copy */

export interface StripPreferences {
  thresholds: StripThresholds;
  hidden: readonly string[];
}

let current: StripPreferences = { thresholds: DEFAULT_STRIP_THRESHOLDS, hidden: [] };
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

/** Called whenever the effective preferences arrive or change (sign-in, a save in Settings). */
export function applyStripPreferences(effective: PreferencesDTO["effective"] | Effective | null | undefined): void {
  current = { thresholds: stripThresholdsFrom(effective as Effective), hidden: hiddenFrom(effective as Effective) };
  emit();
}

export function stripPreferencesSnapshot(): StripPreferences {
  return current;
}

/** Update the local copy at once (the save to the server follows). */
export function setLocalHidden(hidden: readonly string[]): string {
  const stored = serializeHidden(hidden);
  current = { ...current, hidden: stored ? stored.split("\n") : [] };
  emit();
  return stored;
}

export function useStripPreferences(): StripPreferences {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => current,
    () => current,
  );
}
