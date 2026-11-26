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
  /**
   * Whether the name is one the trader knows (a contract, route or price this page can name). A
   * fallback (kind and id, or a free-text evidence line the server lists with its references) is
   * kept for the identifiers disclosure, not shown as a name.
   */
  named: boolean;
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

function nameFor(kind: string, id: string, lookup: LineageLookup, t: Translate): { name: string; named: boolean } {
  const kindWord = KIND_KEY[kind] ? t(KIND_KEY[kind]) : null;
  if (kind === "upstream_resource_contract" || kind === "portfolio_resource") {
    const name = lookup.resources?.get(id);
    if (name) return { name: kindWord && kind === "upstream_resource_contract" ? `${name} ${kindWord.toLowerCase()}` : name, named: true };
  }
  if (kind === "route_candidate") {
    const name = lookup.routes?.get(id);
    if (name) return { name, named: true };
  }
  if (kind === "market_observation") {
    const name = observationName(id);
    if (name) return { name: t("lineage.price_of", { name }), named: true };
  }
  // Unknown to this page: the kind in words and the id, never the raw `kind:id` pair.
  return { name: kindWord ? `${kindWord} ${id}` : id || kind, named: false };
}

/** A record reference is `snake_case_kind:id`; anything else is an evidence line, not a record. */
const RECORD_KIND = /^[a-z][a-z0-9_]*$/;

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
    if (colon > 0 && RECORD_KIND.test(kind)) {
      result.push({ ref, ...nameFor(kind, id, lookup, t) });
    } else if (colon < 0 && RECORD_KIND.test(kind)) {
      result.push({ ref, name: KIND_KEY[kind] ? t(KIND_KEY[kind]) : kind.replace(/_/g, " "), named: Boolean(KIND_KEY[kind]) });
    } else {
      result.push({ ref, name: "", named: false });
    }
  }
  return result;
}

/** A resource id in words, or the id when this page does not know it. */
export function resourceName(id: string, lookup: LineageLookup): string {
  return lookup.resources?.get(id) ?? id;
}
