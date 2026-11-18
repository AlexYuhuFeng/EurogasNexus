import type { ReactNode } from "react";

/** At most this many missing items are shown (design basis H.1). */
export const READINESS_MAX_ITEMS = 3;

export interface ReadinessItem {
  id: string;
  /** What is needed, in desk words: "A price for TTF Dec-26". */
  label: ReactNode;
  ready: boolean;
  /** Why it is missing, when it is: "No close since 14 Nov". */
  state?: ReactNode;
  /** The one control that fixes it (a link or Button); for a permission, who grants it. */
  fix?: ReactNode;
}

/** The items to show: the missing ones, at most three, in the order given. */
export function missingReadiness(items: readonly ReadinessItem[]): ReadinessItem[] {
  return items.filter((item) => !item.ready).slice(0, READINESS_MAX_ITEMS);
}
