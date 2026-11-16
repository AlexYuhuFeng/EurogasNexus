/**
 * Lineage references in plain words (UX_REFERENCE rule 3).
 *
 * A warning rests on records the server names by kind and id
 * (`upstream_resource_contract:demo-haldor-24`, `market_observation:demo-TTF-ma-1`). On screen the
 * trader reads the names they know ("Haldor supply (Easington)", "TTF MA price"); the identifiers
 * stay one disclosure away for support.
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface LineageLookup {
  /** Resource and contract ids to their names. */
  resources?: ReadonlyMap<string, string>;
  /** Route ids to their names. */
  routes?: ReadonlyMap<string, string>;
}

export interface LineageName {
  /** The reference as the server sent it (kept for the disclosure and support). */
  ref: string;
  /** What a trader reads. */
  name: string;
}

const KIND_KEY: Record<string, string> = {
  upstream_resource_contract: "lineage.kind.contract",
  portfolio_resource: "lineage.kind.resource",
  route_candidate: "lineage.kind.route",
  market_observation: "lineage.kind.price",
  route_template: "lineage.kind.route_template",
  demo_route_template: "lineage.kind.route_template",
};

/** "demo-TTF-ma-1" → "TTF MA": the hub and product of a market observation id. */
function observationName(id: string): string | null {
  const match = /^(?:demo-)?([A-Za-z]{2,6})-([A-Za-z]{2,4})(?:-\d+)?$/.exec(id);
  if (!match) return null;
  return `${match[1].toUpperCase()} ${match[2].toUpperCase()}`;
}

function nameFor(kind: string, id: string, lookup: LineageLookup, t: Translate): string {
  const kindWord = KIND_KEY[kind] ? t(KIND_KEY[kind]) : null;
  if (kind === "upstream_resource_contract" || kind === "portfolio_resource") {
    const name = lookup.resources?.get(id);
    if (name) return kindWord && kind === "upstream_resource_contract" ? `${name} ${kindWord.toLowerCase()}` : name;
  }
  if (kind === "route_candidate") {
    const name = lookup.routes?.get(id);
    if (name) return name;
  }
  if (kind === "market_observation") {
    const name = observationName(id);
    if (name) return t("lineage.price_of", { name });
  }
  // Unknown to this page: the kind in words and the id, never the raw `kind:id` pair.
  return kindWord ? `${kindWord} ${id}` : id || kind;
}

/** The names of a list of lineage references, in order, without duplicates. */
export function lineageNames(refs: readonly string[], lookup: LineageLookup, t: Translate): LineageName[] {
  const seen = new Set<string>();
  const result: LineageName[] = [];
  for (const ref of refs) {
    if (!ref || seen.has(ref)) continue;
    seen.add(ref);
    const colon = ref.indexOf(":");
    const kind = colon > 0 ? ref.slice(0, colon) : ref;
    const id = colon > 0 ? ref.slice(colon + 1) : "";
    const bare = KIND_KEY[kind] ? t(KIND_KEY[kind]) : kind.replace(/_/g, " ");
    result.push({ ref, name: colon > 0 ? nameFor(kind, id, lookup, t) : bare });
  }
  return result;
}

/** A resource id in words, or the id when this page does not know it. */
export function resourceName(id: string, lookup: LineageLookup): string {
  return lookup.resources?.get(id) ?? id;
}
