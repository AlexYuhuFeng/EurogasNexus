import type { NormalizedMarketObsDTO } from "../../api/client.ts";

export interface StrategyPriceChoice { name: string; description: string }

/** Names are server supplied, never guessed from a display label. A name may
 * represent several sources; this picker does not promise source binding. */
export function strategyPriceCatalogue(rows: NormalizedMarketObsDTO[], leg?: "day_ahead" | "intraday", hubs?: string): StrategyPriceChoice[] {
  const allowedHubs = (hubs ?? "").split(",").map((hub) => hub.trim().toUpperCase()).filter(Boolean);
  const groups = new Map<string, Set<string>>();
  for (const row of rows) {
    if (!row.is_gas_price || !row.price_name?.trim()) continue;
    if (allowedHubs.length && !allowedHubs.includes(row.hub.toUpperCase())) continue;
    const tenor = row.tenor.toLowerCase().replace(/[ _]/g, "-");
    if (leg === "day_ahead" && !/day-?ahead/.test(tenor)) continue;
    if (leg === "intraday" && !/within-?day|intra-?day/.test(tenor)) continue;
    const descriptions = groups.get(row.price_name) ?? new Set<string>();
    descriptions.add([row.source_system, row.hub, row.tenor, row.unit.startsWith(`${row.currency}/`) ? row.unit : `${row.currency} · ${row.unit}`].filter(Boolean).join(" · "));
    groups.set(row.price_name, descriptions);
  }
  return [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([name, descriptions]) => ({
    name, description: [...descriptions].sort().join("; "),
  }));
}
