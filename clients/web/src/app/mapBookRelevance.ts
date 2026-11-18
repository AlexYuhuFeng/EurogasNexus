/**
 * The "Our book" view's emphasis and its "why" lines (design basis 2, J.5). Kept free of app
 * imports so it can be tested directly.
 *
 * The server derives three relevance classes from the store and the pricing graph
 * (`application/map_book.py`): **ours** (the deals' delivery points, hubs, priced paths, held
 * capacity and storage, expected cargoes and their terminals, held slots), **reachable**
 * (neighbouring market areas within two crossings along the proven adjacency, with published
 * tariffs and an indicative spread net of them) and **opportunity** (from the opportunity core,
 * none until it lands). This module turns them into what the map draws and what a selection
 * says: everything else dims.
 */
import type { BookReachableDTO, BookReasonDTO, BookRelevanceDTO } from "../api/client";
import { formattingLocale } from "./time/timeFormat";
import { bookFlowWidth, compactMwhPerDay, polyline, type BookFlowLine, type LegPath, type LineEndpoint, type LineCoordinate } from "./mapLineGeometry";

export type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface BookEmphasis {
  /** Node ids of the deals' places, hubs and the points on their priced paths. */
  ours: Set<string>;
  /** Node ids on a path to a reachable neighbouring market area (and its hub), not ours. */
  reachable: Set<string>;
}

export const NO_BOOK_EMPHASIS: BookEmphasis = { ours: new Set(), reachable: new Set() };

export function bookEmphasis(relevance: BookRelevanceDTO | null | undefined): BookEmphasis {
  if (!relevance) return NO_BOOK_EMPHASIS;
  const ours = new Set<string>();
  for (const item of relevance.ours) if (item.kind !== "cargo") ours.add(item.ref);
  for (const path of relevance.contract_paths) path.path_node_ids.forEach((id) => ours.add(id));
  const reachable = new Set<string>();
  for (const path of relevance.reachable) {
    for (const id of path.path_node_ids) if (!ours.has(id)) reachable.add(id);
  }
  return { ours, reachable };
}

/** Our contracts' priced paths as book lines: width by contract volume, along the drawn legs. */
export function contractPathLines(
  relevance: BookRelevanceDTO | null | undefined,
  nodes: ReadonlyMap<string, LineEndpoint>,
  legPath?: LegPath,
): BookFlowLine[] {
  const byPair = new Map<string, BookFlowLine>();
  for (const path of relevance?.contract_paths ?? []) {
    const points = path.path_node_ids.map((id) => nodes.get(id));
    if (points.length < 2 || points.some((point) => !point || !Number.isFinite(point.lon) || !Number.isFinite(point.lat))) continue;
    const fromId = path.path_node_ids[0];
    const toId = path.path_node_ids[path.path_node_ids.length - 1];
    const key = `${fromId}->${toId}`;
    const volume = path.mwh_d ?? 0;
    const existing = byPair.get(key);
    if (existing) {
      existing.mwhPerDay += volume;
      existing.pathCount += 1;
      existing.routeIds.push(path.contract_id);
      continue;
    }
    byPair.set(key, {
      id: `book-contract-${key}`,
      fromId,
      toId,
      mwhPerDay: volume,
      width: 0,
      label: "",
      routeIds: [path.contract_id],
      pathCount: 1,
      geometryBasis: "priced_path",
      coordinates: polyline(points as LineEndpoint[], legPath),
    });
  }
  return [...byPair.values()].map((line) => ({
    ...line,
    width: bookFlowWidth(line.mwhPerDay),
    label: line.mwhPerDay > 0 ? compactMwhPerDay(line.mwhPerDay) : "",
  }));
}

/** Paths to reachable neighbouring market areas, drawn at medium emphasis. */
export function reachablePathLines(
  relevance: BookRelevanceDTO | null | undefined,
  nodes: ReadonlyMap<string, LineEndpoint>,
  legPath?: LegPath,
): Array<{ id: string; toHub: string; coordinates: LineCoordinate[] }> {
  const out: Array<{ id: string; toHub: string; coordinates: LineCoordinate[] }> = [];
  for (const path of relevance?.reachable ?? []) {
    const points = path.path_node_ids.map((id) => nodes.get(id));
    if (points.length < 2 || points.some((point) => !point || !Number.isFinite(point.lon))) continue;
    out.push({ id: `book-reach-${path.from_hub}-${path.to_hub}`, toHub: path.to_hub, coordinates: polyline(points as LineEndpoint[], legPath) });
  }
  return out;
}

const gbp = (value: number | null) => (value === null ? "–" : value.toFixed(2));

/** "Reachable from TTF via BBL: spread a, tariff b, net c GBP/MWh (indicative, sim)". */
export function reachableLine(path: BookReachableDTO, t: Translate): string {
  const via = path.via.join(", ");
  const tag = t(path.simulated ? "map.book.indicative_sim" : "map.book.indicative");
  if (path.net_gbp_mwh !== null) {
    return t("map.book.reason.reachable_net", {
      from: path.from_hub,
      to: path.to_hub,
      via,
      spread: gbp(path.spread_gbp_mwh),
      tariff: gbp(path.tariff_gbp_mwh),
      net: gbp(path.net_gbp_mwh),
      tag,
    });
  }
  const gaps: string[] = [];
  if (path.tariff_status !== "held") {
    gaps.push(
      path.missing_legs && path.missing_legs.length
        ? t("map.book.gap.tariff_legs", { legs: path.missing_legs.join("; ") })
        : t("map.book.gap.tariff"),
    );
  }
  if (!path.price_from || !path.price_to) gaps.push(t("map.book.gap.price"));
  return t("map.book.reason.reachable_gap", {
    from: path.from_hub,
    to: path.to_hub,
    via,
    spread: gbp(path.spread_gbp_mwh),
    gaps: gaps.join("; "),
    tag,
  });
}

/** A whole number in the app language's grouping (never the browser's locale). */
function num(value: unknown, language: string): string {
  return typeof value === "number" ? Math.round(value).toLocaleString(formattingLocale(language)) : "–";
}

function when(value: unknown): string {
  return typeof value === "string" && value ? value.slice(0, 16).replace("T", " ") : "–";
}

/** One reason, as the desk would say it. */
export function reasonLine(reason: BookReasonDTO, t: Translate, language = "en"): string {
  switch (reason.key) {
    case "delivery_point":
      return t(reason.counterparty ? "map.book.reason.delivery_point_cp" : "map.book.reason.delivery_point", {
        contract: reason.contract,
        counterparty: reason.counterparty,
        mwh: num(reason.mwh_d, language),
      });
    case "contract_hub":
      return t("map.book.reason.contract_hub", { contract: reason.contract });
    case "contract_path":
      return t("map.book.reason.contract_path", { contract: reason.contract, from: reason.from_hub, to: reason.to_hub });
    case "held_capacity":
      return t("map.book.reason.held_capacity", {
        contract: reason.contract,
        mwh: num(reason.mwh_d, language),
        direction: String(reason.direction ?? "").toLowerCase(),
      });
    case "held_storage":
      return t("map.book.reason.held_storage", { mwh: num(reason.max_inventory_mwh, language), hub: reason.hub });
    case "expected_cargo":
      return t("map.book.reason.expected_cargo", { vessel: reason.vessel, eta: when(reason.eta_utc), terminal: reason.terminal ?? "–" });
    case "regas_slot":
      return t("map.book.reason.regas_slot", { start: when(reason.window_start_utc), end: when(reason.window_end_utc) });
    default:
      return reason.key;
  }
}

/**
 * Why the selected object is on the book view: the reasons of every "ours" item at its
 * nodes (or its hub, or its cargo), then the reachable paths it ends or lies on.
 */
export function bookReasonLines(
  relevance: BookRelevanceDTO | null | undefined,
  selected: { nodeIds: readonly string[]; cargoId?: string | null },
  t: Translate,
  language = "en",
): string[] {
  if (!relevance) return [];
  const ids = new Set(selected.nodeIds);
  const lines: string[] = [];
  for (const item of relevance.ours) {
    const hit = item.kind === "cargo" ? item.ref === selected.cargoId : ids.has(item.ref);
    if (!hit) continue;
    for (const reason of item.reasons) {
      const line = reasonLine(reason, t, language);
      if (!lines.includes(line)) lines.push(line);
    }
  }
  const passing: string[] = [];
  for (const path of relevance.reachable) {
    // A selected hub is the far end of the path (its node is the path's last).
    const endsHere = ids.has(path.path_node_ids[path.path_node_ids.length - 1] ?? "");
    const onPath = path.crossings.some((crossing) => crossing.node_id && ids.has(crossing.node_id));
    if (endsHere) lines.push(reachableLine(path, t));
    else if (onPath) passing.push(`${path.from_hub} → ${path.to_hub}`);
  }
  // One line for the reachable paths that pass here, not one per path.
  if (passing.length) lines.push(t("map.book.reason.on_reachable_path", { paths: passing.join(", ") }));
  return lines;
}
