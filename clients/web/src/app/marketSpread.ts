/**
 * Directional hub spreads, resolved deterministically and with a stated sign convention.
 *
 * Why this module exists
 * ----------------------
 * `MarketTerminal` used to index the `/api/market/spreads` rows by hub pair and period
 * alone, discarding `from_venue`/`to_venue`:
 *
 * ```
 * direct.set(`${row.from_hub}:${row.to_hub}:${row.period}`, row.spread_eur_mwh)
 * reverse.set(`${row.to_hub}:${row.from_hub}:${row.period}`, row.spread_eur_mwh)
 * ```
 *
 * A single hub pair and period is not unique in that response: the seeded day-ahead
 * TTF/NBP pair arrives six times, once per venue combination, with six different values
 * between 2.0578 and 2.1928. Each iteration overwrote the previous one, so the number a
 * trader saw was whichever row the API happened to return last. A probe that reversed
 * only the row order changed the displayed value without a single market value changing.
 *
 * The lookup then negated the reverse entry, so the sign depended on which direction the
 * surviving row happened to be quoted in. The seeded TTF-to-NBP day-ahead spread is
 * +2.1078, and the screen showed approximately -2.11.
 *
 * The convention this module fixes, and which the UI must state:
 *
 *     spread(from -> to) = price(to) - price(from)
 *
 * so a positive TTF-to-NBP spread means NBP is the more expensive hub. Every value this
 * module returns is that quantity; it never returns a negated amount without saying so,
 * and it always names the venue pair and the direction the value describes.
 *
 * Determinism: rather than "last write wins", rows are ranked. A directly-quoted
 * direction beats a value derived by negating the opposite direction, because the derived
 * value assumes both legs are tradeable at the same instant from the same quotes. Among
 * equally-ranked rows the venue pair is chosen by a stable published order, so an
 * unchanged market produces an unchanged number.
 *
 * Note on the text of this file: it is deliberately ASCII-only. Earlier revisions carried
 * em dashes and arrow characters inside template literals, and a tooling round trip
 * re-encoded them, which silently terminated a template literal and stopped the module
 * from loading at all. Comments only lose a little fluency; a broken literal loses the
 * feature.
 */

import type { MarketSpreadDTO } from "@/api/client";

/** A resolved spread, carrying everything a caller needs to label it honestly. */
export interface ResolvedHubSpread {
  /** `price(to_hub) - price(from_hub)`, in EUR/MWh. */
  value_eur_mwh: number;
  from_hub: string;
  to_hub: string;
  period: string;
  from_venue: string;
  to_venue: string;
  /** True when the value came from the opposite row negated, not from a direct quote. */
  derived_from_reverse: boolean;
}

interface IndexedSpread {
  row: MarketSpreadDTO;
  /** The direction this entry describes, after any negation. */
  from_hub: string;
  to_hub: string;
  /** The venue pair in the direction this entry describes, so a label can be honest. */
  from_venue: string | null;
  to_venue: string | null;
  value: number;
  reversed: boolean;
}

/**
 * Venue preference for equally-ranked rows.
 *
 * The published order is stable, with the two named exchanges first; venues outside the
 * list sort last, so an unknown venue cannot silently outrank a known one.
 */
const VENUE_ORDER = ["EEX", "ICE OCM", "Trayport", "ICE", "PEGAS", "Powernext"];

function normalise(value: string | null | undefined): string {
  return (value ?? "").trim().toUpperCase();
}

function venueRank(venue: string | null | undefined): number {
  const index = VENUE_ORDER.indexOf(normalise(venue));
  return index === -1 ? VENUE_ORDER.length : index;
}

/**
 * Build a resolver over the spread rows.
 *
 * The returned function answers a directional question - "what is the spread from
 * `fromHub` to `toHub` in `period`?" - with at most one answer, or `null` when the
 * response contains no row that can answer it.
 */
export function createHubSpreadResolver(rows: readonly MarketSpreadDTO[]) {
  // Two maps, because a direction is reachable in two ways and they must not compete on
  // the same key. A row `A -> B` answers `A -> B` directly, and it answers `B -> A` only
  // by negation. Collapsing both into one map let a negated reverse entry overwrite a
  // directly quoted one, which is how the sign came to depend on the row order.
  const quoted = new Map<string, IndexedSpread>();
  const negated = new Map<string, IndexedSpread>();

  const key = (from: string, to: string, period: string) =>
    `${normalise(from)}:${normalise(to)}:${period}`;

  /** True when `candidate` should displace `existing` under the ranked comparison. */
  const preferred = (candidate: IndexedSpread, existing: IndexedSpread): boolean => {
    const candidateVenue =
      venueRank(candidate.from_venue) * 100 + venueRank(candidate.to_venue);
    const existingVenue =
      venueRank(existing.from_venue) * 100 + venueRank(existing.to_venue);
    if (candidateVenue !== existingVenue) return candidateVenue < existingVenue;

    const candidateNames = `${normalise(candidate.from_venue)}|${normalise(candidate.to_venue)}`;
    const existingNames = `${normalise(existing.from_venue)}|${normalise(existing.to_venue)}`;
    return candidateNames < existingNames;
  };

  const consider = (bucket: Map<string, IndexedSpread>, candidate: IndexedSpread) => {
    // The period lives on the row; `IndexedSpread` carries only the direction it
    // describes. Reading `candidate.period` here produced keys ending in `:undefined`,
    // so every lookup missed and the resolver answered `null` for data it had.
    const id = key(candidate.from_hub, candidate.to_hub, candidate.row.period);
    const existing = bucket.get(id);
    if (!existing || preferred(candidate, existing)) bucket.set(id, candidate);
  };

  for (const row of rows) {
    if (!row || !row.from_hub || !row.to_hub) continue;
    if (typeof row.spread_eur_mwh !== "number" || !Number.isFinite(row.spread_eur_mwh)) {
      continue;
    }

    const fromHub = normalise(row.from_hub);
    const toHub = normalise(row.to_hub);
    const fromVenue = row.from_venue ?? null;
    const toVenue = row.to_venue ?? null;

    // As published: from -> to equals the quoted amount, with the venues read in the same
    // direction as the pair.
    consider(quoted, {
      row,
      from_hub: fromHub,
      to_hub: toHub,
      from_venue: fromVenue,
      to_venue: toVenue,
      value: row.spread_eur_mwh,
      reversed: false,
    });

    // The same amount read backwards, negated to stay consistent with
    // `price(to) - price(from)`, with the venue pair swapped so a label describes the
    // direction it is attached to.
    consider(negated, {
      row,
      from_hub: toHub,
      to_hub: fromHub,
      from_venue: toVenue,
      to_venue: fromVenue,
      value: -row.spread_eur_mwh,
      reversed: true,
    });
  }

  return function resolve(
    fromHub: string,
    toHub: string,
    period: string,
  ): ResolvedHubSpread | null {
    const id = key(fromHub, toHub, period);
    // A directly quoted direction always wins; negation is the fallback, never a
    // competitor.
    const entry = quoted.get(id) ?? negated.get(id);
    if (!entry) return null;
    return {
      value_eur_mwh: entry.value,
      from_hub: entry.from_hub,
      to_hub: entry.to_hub,
      period: entry.row.period,
      from_venue: entry.from_venue ?? entry.row.from_venue,
      to_venue: entry.to_venue ?? entry.row.to_venue,
      derived_from_reverse: entry.reversed,
    };
  };
}

/**
 * The hub's premium over TTF: `price(hub) - price(TTF)`.
 *
 * This is what the "Regional comparison" card states, and it is deliberately not the
 * same quantity as the directional spread a venue quotes. For NBP against TTF the two
 * are opposite in sign:
 *
 *     price(NBP) - price(TTF)   the premium                     = +2.09
 *     directional TTF -> NBP    the same quantity               = +2.09
 *     directional NBP -> TTF    price(TTF) - price(NBP)         = -2.09
 *
 * A card showing a hub beside the label "spread to TTF" means the first of these, which
 * equals the TTF-to-hub direction. The component previously took the third, from whichever
 * venue row survived the map overwrite, and let it take precedence over a live
 * `mid - mid` figure that had the opposite sign - so a hub trading above TTF rendered as
 * negative, and the sign could flip with the API's row order.
 *
 * Returns `null` when the response carries no row from which the premium can be
 * established. TTF itself has no premium over TTF, so it resolves to a plain zero rather
 * than `null`, matching how the strip displays it.
 */
export function premiumOverTtf(
  rows: readonly MarketSpreadDTO[],
  hub: string,
  period: string,
): ResolvedHubSpread | null {
  const normalisedHub = normalise(hub);
  if (normalisedHub === "TTF") {
    return {
      value_eur_mwh: 0,
      from_hub: "TTF",
      to_hub: "TTF",
      period,
      from_venue: "",
      to_venue: "",
      derived_from_reverse: false,
    };
  }
  return createHubSpreadResolver(rows)("TTF", normalisedHub, period);
}

/**
 * The directional spread `price(to) - price(from)`, as a venue quotes it.
 *
 * Kept separate from {@link premiumOverTtf} because they answer different questions, and
 * a caller that needs one must not silently receive the other.
 */
export function directionalSpread(
  rows: readonly MarketSpreadDTO[],
  fromHub: string,
  toHub: string,
  period: string,
): ResolvedHubSpread | null {
  return createHubSpreadResolver(rows)(fromHub, toHub, period);
}
