/** Places the map can locate, and how the finder ranks them against a query. */

export interface MapFinderPlace {
  id: string;
  name: string;
  /** Short kind shown beside the name: "Hub", "LNG terminal", "Our cargo", ... */
  kind: string;
  lon: number;
  lat: number;
  zoom: number;
}

/** Rank by how a name matches: start of name, start of a word, anywhere. */
export function findPlaces(places: MapFinderPlace[], query: string, limit = 8): MapFinderPlace[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const scored: Array<[number, MapFinderPlace]> = [];
  for (const place of places) {
    const name = place.name.toLowerCase();
    const index = name.indexOf(needle);
    if (index < 0) continue;
    const score = index === 0 ? 0 : /[\s(/-]/.test(name[index - 1]) ? 1 : 2;
    scored.push([score, place]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].name.length - b[1].name.length);
  return scored.slice(0, limit).map(([, place]) => place);
}
