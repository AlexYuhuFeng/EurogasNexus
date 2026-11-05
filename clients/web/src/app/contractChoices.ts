/**
 * The closed lists a contract's terms are chosen from, instead of typed.
 *
 * A delivery or exit point is one the desk can route gas from: a European hub (its virtual
 * trading point) or a point of the route network the backend serves. Typing "NBP Eassington"
 * would silently lose the contract from positions and routing; choosing cannot. A value a
 * stored or imported contract already records is kept as its own option ("as recorded"),
 * so nothing is rewritten by opening it.
 */

import type { RouteCandidateDTO } from "@/api/client";

/** European gas hubs, in desk order (matches the backend's market registry). */
export const GAS_HUBS = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB"] as const;

/** The currency a hub quotes in: NBP in GBP, every continental hub in EUR. */
export function hubCurrency(hub: string | null): "GBP" | "EUR" | null {
  if (!hub) return null;
  return hub === "NBP" ? "GBP" : "EUR";
}

/** Currencies a contract may be priced in. */
export const PRICE_CURRENCIES = ["GBP", "EUR", "USD"] as const;
export type PriceCurrency = (typeof PRICE_CURRENCIES)[number];

/**
 * The currency a contract's price is recorded in: the one chosen, else the delivery hub's own,
 * else GBP (every contract recorded before the currency existed was priced in GBP).
 */
export function contractPriceCurrency(chosen: string | null | undefined, deliveryPoint: string): PriceCurrency {
  const code = (chosen ?? "").trim().toUpperCase();
  if ((PRICE_CURRENCIES as readonly string[]).includes(code)) return code as PriceCurrency;
  return hubCurrency(hubOfPoint(deliveryPoint)) ?? "GBP";
}

/** The hub a point name belongs to ("NBP St Fergus" is NBP), or null when it names none. */
export function hubOfPoint(point: string): string | null {
  const upper = (point || "").toUpperCase();
  return GAS_HUBS.find((hub) => upper.includes(hub)) ?? null;
}

/** Hubs first, then every point the route network names, each once. */
export function pointOptions(routes: readonly RouteCandidateDTO[]): string[] {
  const network = new Set<string>();
  for (const route of routes) {
    for (const point of [
      route.start_point_name,
      route.target_point_name,
      route.required_entry_point_name,
      route.required_exit_point_name,
    ]) {
      const name = (point ?? "").trim();
      if (name && !(GAS_HUBS as readonly string[]).includes(name)) network.add(name);
    }
  }
  return [...GAS_HUBS, ...[...network].sort((a, b) => a.localeCompare(b))];
}

/** The options plus the recorded value when it is not one of them. */
export function withRecorded(options: readonly string[], recorded: string): string[] {
  const value = recorded.trim();
  return value && !options.includes(value) ? [...options, value] : [...options];
}

/** Sale routes the resource-pool scenarios understand. */
export const SALE_MODES = ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE", "REROUTE_SALE"] as const;

/** Governing laws of the EFET and bilateral agreements desks sign. */
export const GOVERNING_LAWS = [
  "English law",
  "Dutch law",
  "German law",
  "French law",
  "Belgian law",
  "Italian law",
  "Austrian law",
  "Swiss law",
] as const;

/** Price bases for a contract delivered at `hub`. */
export function indexOptions(hub: string | null): string[] {
  const base = hub ?? "TTF";
  return [
    "Fixed price",
    `${base} day-ahead`,
    `${base} month-ahead`,
    `${base} season-ahead`,
    `${base} gas-year ahead`,
    "Oil-indexed",
  ];
}
