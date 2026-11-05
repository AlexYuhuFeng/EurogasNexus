/**
 * Which routes on the map matter to the firm's book. Kept free of app imports so it can be
 * tested directly.
 */
/** What the book uses: the routes its allocations flow on, and the sites it delivers at. */
export interface RoutesThatMatter {
  routeIds: ReadonlySet<string>;
  edgeIds: ReadonlySet<string>;
  pointIds: ReadonlySet<string>;
}

export const NO_ROUTES_MATTER: RoutesThatMatter = { routeIds: new Set(), edgeIds: new Set(), pointIds: new Set() };

/**
 * Whether a line carries or reaches the firm's own business. Routes are context and draw
 * dimmed; a route matters (and is drawn bright) when an allocation flows on it, for
 * example NBP to TTF through IUK or through BBL, whichever the decision chose, or when it
 * lands gas at a site where the book has a live contract, regas slot or cargo.
 */
export function lineMatters(
  line: { routeId?: string | null; edge: { id: string } | null; from: { id: string }; to: { id: string } },
  matter: RoutesThatMatter,
): boolean {
  if (line.routeId && matter.routeIds.has(line.routeId)) return true;
  if (line.edge && matter.edgeIds.has(line.edge.id)) return true;
  return matter.pointIds.has(line.from.id) || matter.pointIds.has(line.to.id);
}

/**
 * The routes the decision's allocations use, by route and by pipeline segment. A candidate
 * the optimiser did not choose and a blocked route do not matter yet.
 */
export function routesInUse(
  paths: ReadonlyArray<{ routeId: string; routeState: string; allocatedQuantityMwhPerDay: number | null }>,
  edgesByRouteId: ReadonlyMap<string, ReadonlyArray<{ id: string }>>,
): { routeIds: string[]; edgeIds: string[] } {
  const routeIds = new Set<string>();
  const edgeIds = new Set<string>();
  for (const path of paths) {
    if (path.routeState !== "allocated" || !(path.allocatedQuantityMwhPerDay ?? 0)) continue;
    if (!path.routeId) continue;
    routeIds.add(path.routeId);
    for (const edge of edgesByRouteId.get(path.routeId) ?? []) edgeIds.add(edge.id);
  }
  return { routeIds: [...routeIds], edgeIds: [...edgeIds] };
}
