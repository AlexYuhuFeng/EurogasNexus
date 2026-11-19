/**
 * First-use hints (design basis H.1): at most three per page, anchored to real controls, shown
 * once per person (the `hints_seen` preference), replayable from Account -> Preferences. Pure, so
 * the rules are tested without a browser.
 */

/** At most this many hints a page may declare. */
export const MAX_HINTS_PER_PAGE = 3;

export interface FirstUseHint {
  /** Stable id, `<mode>.<task>.<what>` ("desk.today.brief"). */
  id: string;
  /** CSS selector of the control the hint is about; a hint whose control is absent is skipped. */
  anchor: string;
  /** i18n key of the one-sentence hint. */
  textKey: string;
}

/** The ids a stored `hints_seen` value holds. */
export function parseSeen(value: string | null | undefined): Set<string> {
  return new Set(String(value ?? "").split(",").map((item) => item.trim()).filter(Boolean));
}

/** The stored value for a set of seen ids, in a stable order. */
export function serialiseSeen(seen: Iterable<string>): string {
  return [...new Set(seen)].sort().join(",");
}

/**
 * The hints still to show on a page, in the order declared, at most three; none when hints are
 * switched off on this device (the acceptance sweep's own setting).
 */
export function hintsToShow(
  hints: readonly FirstUseHint[],
  seen: ReadonlySet<string>,
  { off = false }: { off?: boolean } = {},
): FirstUseHint[] {
  if (off) return [];
  return hints.slice(0, MAX_HINTS_PER_PAGE).filter((hint) => !seen.has(hint.id));
}

/** The seen set after "replay this page's hints": its ids forgotten, every other page's kept. */
export function replayPage(seen: ReadonlySet<string>, pagePrefix: string): Set<string> {
  return new Set([...seen].filter((id) => !id.startsWith(`${pagePrefix}.`)));
}
