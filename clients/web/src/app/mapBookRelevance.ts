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
import type {
  BookContractPeriodDTO,
  BookDisruptionDTO,
  BookOpportunityPathDTO,
  BookReachableDTO,
  BookReasonDTO,
  BookRelevanceDTO,
  MapCargoDTO,
  MapRegasSlotDTO,
} from "../api/client";
import { formatGasDay, formattingLocale } from "./time/timeFormat.ts";
import { bookFlowWidth, compactMwhPerDay, polyline, type BookFlowLine, type LegPath, type LineEndpoint, type LineCoordinate } from "./mapLineGeometry.ts";

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
  // An opportunity's path pops out with ours.
  for (const path of relevance.opportunities ?? []) path.path_node_ids.forEach((id) => ours.add(id));
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
      // Contracts sharing a line split it only when they share the window.
      if (!samePeriod(existing.period ?? null, path.period ?? null)) existing.period = null;
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
      period: path.period ?? null,
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

export interface OpportunityPathLine {
  id: string;
  opportunityId: string;
  emphasis: "pop" | "outline";
  coordinates: LineCoordinate[];
  /** The far hub, where the headline is labelled. */
  labelAt: LineCoordinate;
  label: string;
}

/** The core's headline as the map labels it: "L +1.25 EUR/MWh", "sim" when simulated. */
/** A margin as a desk reads it: signed, three decimals (+0.238), "–" when not stated. */
export function signedMargin(value: string | number | null | undefined): string {
  const number = typeof value === "number" ? value : value === null || value === undefined ? Number.NaN : Number(value);
  if (!Number.isFinite(number)) return "–";
  const text = Math.abs(number).toFixed(3);
  return `${number < 0 ? "-" : "+"}${text}`;
}

export function opportunityLabel(item: BookOpportunityPathDTO): string {
  const signed = signedMargin(item.headline.value);
  return `${item.type_code} ${signed} ${item.headline.unit}${item.simulated ? " sim" : ""}`;
}

/** Time left to act, "2 h 10 min" / "12 min" / "3 d 4 h"; null when closed or not stated. */
export function windowLeft(closesUtc: string | null | undefined, nowMs: number): string | null {
  if (!closesUtc) return null;
  const left = Date.parse(closesUtc) - nowMs;
  if (!Number.isFinite(left) || left <= 0) return null;
  const minutes = Math.ceil(left / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const rest = minutes % 60;
  if (days > 0) return `${days} d ${hours} h`;
  if (hours > 0) return `${hours} h ${rest} min`;
  return `${rest} min`;
}

/** Whether an opportunity's window to act has closed (it is then not drawn). */
export function windowClosed(item: Pick<BookOpportunityPathDTO, "window_closes_utc">, nowMs: number): boolean {
  return Boolean(item.window_closes_utc) && Date.parse(item.window_closes_utc!) <= nowMs;
}

/** The opportunities' paths along the drawn legs, labelled on the far hub. */
/**
 * Opportunities on the same path (one per delivery month, say) are one line: the strongest
 * stands for the others ("L +0.355 EUR/MWh ×14"); the list and the card name them all.
 */
export function groupOpportunities(items: readonly BookOpportunityPathDTO[]): Array<{ lead: BookOpportunityPathDTO; members: BookOpportunityPathDTO[] }> {
  const groups = new Map<string, BookOpportunityPathDTO[]>();
  for (const item of items) {
    const key = `${item.type_code}|${item.path_node_ids.join(">")}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  const strength = (item: BookOpportunityPathDTO) =>
    (item.emphasis === "pop" ? 1e9 : 0) + Number(item.headline.value ?? Number.NEGATIVE_INFINITY);
  return [...groups.values()].map((members) => ({
    lead: [...members].sort((a, b) => strength(b) - strength(a))[0],
    members,
  }));
}

export function opportunityPathLines(
  relevance: BookRelevanceDTO | null | undefined,
  nodes: ReadonlyMap<string, LineEndpoint>,
  legPath?: LegPath,
  hidden: ReadonlySet<string> = new Set(),
): OpportunityPathLine[] {
  const out: OpportunityPathLine[] = [];
  const shown = (relevance?.opportunities ?? []).filter((item) => !hidden.has(item.opportunity_id));
  for (const { lead: item, members } of groupOpportunities(shown)) {
    const points = item.path_node_ids.map((id) => nodes.get(id));
    if (points.length < 2 || points.some((point) => !point || !Number.isFinite(point.lon))) continue;
    const far = points[points.length - 1]!;
    out.push({
      id: `book-opportunity-${item.opportunity_id}`,
      opportunityId: item.opportunity_id,
      emphasis: item.emphasis,
      coordinates: polyline(points as LineEndpoint[], legPath),
      labelAt: [far.lon, far.lat],
      label: `${opportunityLabel(item)}${members.length > 1 ? ` ×${members.length}` : ""}`,
    });
  }
  return out;
}

const gbp = (value: number | null) => (value === null ? "–" : value.toFixed(2));

/** "Reachable from TTF via BBL: spread a, tariff b, net c GBP/MWh (indicative, sim)". */
export function reachableLine(path: BookReachableDTO, t: Translate): string {
  const via = path.via.join(", ");
  const tag = t(path.simulated ? "map.book.indicative_sim" : "map.book.indicative")
    + (path.with_held_capacity ? ` · ${t("map.book.with_held_capacity")}` : "");
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
    case "pipeline_end":
      return t("map.book.reason.pipeline_end", { pipeline: reason.pipeline, point: reason.point });
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

function samePeriod(a: BookContractPeriodDTO | null, b: BookContractPeriodDTO | null): boolean {
  return !!a && !!b && a.start === b.start && a.end === b.end;
}

/* ------------------------------------------------------------------ done and to go */

/** The share of a window elapsed, 0..1, or null without one. */
export function periodFraction(period: BookContractPeriodDTO | null | undefined): number | null {
  if (!period || !(period.total_days > 0)) return null;
  return Math.min(1, Math.max(0, period.elapsed_days / period.total_days));
}

function segmentLength(a: LineCoordinate, b: LineCoordinate): number {
  // Degrees scaled by the latitude: enough to place a split along a drawn line.
  const kx = Math.cos((((a[1] + b[1]) / 2) * Math.PI) / 180);
  return Math.hypot((b[0] - a[0]) * kx, b[1] - a[1]);
}

/**
 * A line cut at a share of its length: the part done (solid) and the part to go (dashed).
 * The cut point is on both halves, so they meet.
 */
export function splitAtFraction(coordinates: readonly LineCoordinate[], fraction: number): { done: LineCoordinate[]; toGo: LineCoordinate[] } {
  if (coordinates.length < 2) return { done: [...coordinates], toGo: [] };
  const share = Math.min(1, Math.max(0, fraction));
  const lengths = coordinates.slice(1).map((point, index) => segmentLength(coordinates[index], point));
  const total = lengths.reduce((sum, value) => sum + value, 0);
  if (total === 0 || share >= 1) return { done: [...coordinates], toGo: [] };
  if (share <= 0) return { done: [], toGo: [...coordinates] };
  let left = share * total;
  for (let index = 0; index < lengths.length; index += 1) {
    if (left <= lengths[index]) {
      const a = coordinates[index];
      const b = coordinates[index + 1];
      const r = lengths[index] === 0 ? 0 : left / lengths[index];
      const cut: LineCoordinate = [a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r];
      return { done: [...coordinates.slice(0, index + 1), cut], toGo: [cut, ...coordinates.slice(index + 1)] };
    }
    left -= lengths[index];
  }
  return { done: [...coordinates], toGo: [] };
}

/** The point at a share of a line's length (a label's anchor). */
export function pointAtFraction(coordinates: readonly LineCoordinate[], fraction: number): LineCoordinate | null {
  if (!coordinates.length) return null;
  const { done } = splitAtFraction(coordinates, fraction);
  return done.length ? done[done.length - 1] : coordinates[0];
}

function shortDate(iso: string | null | undefined, language: string): string {
  // A day as the desk writes it ("28 Nov", "11月28日"), from the instant's UTC date.
  return iso ? formatGasDay(iso.slice(0, 10), language) : "–";
}

/** "Delivered 49 of 365 days · 1 Oct – 1 Oct (2026/27)". */
export function periodLine(period: BookContractPeriodDTO, t: Translate, language = "en"): string {
  return t("map.book.progress_delivered", {
    elapsed: period.elapsed_days,
    total: period.total_days,
    start: shortDate(period.start, language),
    end: shortDate(period.end, language),
    label: period.label,
  });
}

/**
 * An own cargo's voyage: the share sailed, the ETA and how it sits against its regas slot
 * ("ETA 14 Jan, 1 day late for the slot").
 */
export function cargoProgress(
  cargo: Pick<MapCargoDTO, "cargo_id" | "departed_at_utc" | "eta_utc">,
  slots: readonly Pick<MapRegasSlotDTO, "cargo_id" | "window_start_utc" | "window_end_utc">[],
  nowMs: number,
  t: Translate,
  language = "en",
): { fraction: number | null; line: string } {
  const departed = cargo.departed_at_utc ? Date.parse(cargo.departed_at_utc) : Number.NaN;
  const eta = cargo.eta_utc ? Date.parse(cargo.eta_utc) : Number.NaN;
  const fraction = Number.isFinite(departed) && Number.isFinite(eta) && eta > departed
    ? Math.min(1, Math.max(0, (nowMs - departed) / (eta - departed)))
    : null;
  const etaText = shortDate(cargo.eta_utc, language);
  const slot = slots.find((item) => item.cargo_id === cargo.cargo_id);
  if (!slot || !Number.isFinite(eta)) return { fraction, line: t("map.book.cargo_eta", { eta: etaText }) };
  const day = 86_400_000;
  const opens = Date.parse(slot.window_start_utc);
  const closes = Date.parse(slot.window_end_utc);
  if (eta > opens + day / 2) {
    const late = Math.max(1, Math.round((eta - opens) / day));
    const key = eta > closes ? "map.book.cargo_after_slot" : "map.book.cargo_late";
    return { fraction, line: t(key, { eta: etaText, count: late }) };
  }
  if (eta < opens - day / 2) {
    return { fraction, line: t("map.book.cargo_early", { eta: etaText, count: Math.round((opens - eta) / day) }) };
  }
  return { fraction, line: t("map.book.cargo_on_slot", { eta: etaText }) };
}

/* ------------------------------------------------------------------ disruptions */

/** A disruption's place on the map; only one touching our contracts and active pulses. */
export interface DisruptionMark {
  id: string;
  at: LineCoordinate;
  pulse: boolean;
  active: boolean;
}

export function disruptionMarks(relevance: BookRelevanceDTO | null | undefined): DisruptionMark[] {
  return (relevance?.disruptions ?? [])
    .filter((item) => Number.isFinite(item.location?.lon) && Number.isFinite(item.location?.lat))
    .map((item) => ({ id: item.event_id, at: [item.location.lon, item.location.lat], pulse: item.pulse, active: item.status === "active" }));
}

/**
 * What a disruption callout says: what, until when, and how much of ours it touches
 * ("Out until 28 Nov · 2 of our contracts, 18,000 MWh/d affected").
 */
export function disruptionCallout(item: BookDisruptionDTO, t: Translate, language = "en"): { title: string; lines: string[] } {
  const lines: string[] = [];
  const until = shortDate(item.end_utc, language);
  lines.push(
    item.status === "active"
      ? item.end_utc ? t("map.book.disruption_out_until", { until }) : t("map.book.disruption_out")
      : t("map.book.disruption_planned", { from: shortDate(item.start_utc, language), until }),
  );
  if (item.contracts.length) {
    lines.push(t("map.book.disruption_touches", {
      count: item.contracts.length,
      mwh: Math.round(item.affected_mwh_d).toLocaleString(formattingLocale(language)),
    }));
  } else {
    lines.push(t(`map.book.disruption_touches_${item.touches}`));
  }
  if (item.placement === "zone") lines.push(t("map.book.disruption_zone", { hub: item.hub ?? "–" }));
  const title = `${item.facility_name ?? item.event_id}${item.simulated ? " · sim" : ""}`;
  return { title, lines };
}

/* ------------------------------------------------------------------ re-route proposals */

export interface ProposalLine {
  id: string;
  opportunityId: string;
  /** The way the volume goes now (one point when it is sold where it is delivered). */
  current: LineCoordinate[];
  proposed: LineCoordinate[];
  /** The benefit in our terms, on the proposed line. */
  label: string;
  labelAt: LineCoordinate;
}

/** "via Zeebrugge, +0.35 EUR/MWh after tariffs", or "avoids the outage". */
export function benefitLabel(item: BookOpportunityPathDTO, t: Translate): string {
  const benefit = item.proposal?.benefit;
  if (!benefit) return opportunityLabel(item);
  if (benefit.avoids_outage) return t("map.book.benefit_avoids_outage");
  const signed = signedMargin(benefit.headline.value);
  const figure = `${signed} ${benefit.headline.unit}${item.simulated ? " sim" : ""}`;
  return benefit.via ? t("map.book.benefit_via", { via: benefit.via, figure }) : t("map.book.benefit", { figure });
}

/** The opportunities that state the current way, as a current and a proposed line. */
export function proposalLines(
  relevance: BookRelevanceDTO | null | undefined,
  nodes: ReadonlyMap<string, LineEndpoint>,
  t: Translate,
  legPath?: LegPath,
): ProposalLine[] {
  const out: ProposalLine[] = [];
  for (const item of relevance?.opportunities ?? []) {
    const proposal = item.proposal;
    if (!proposal) continue;
    const proposedPoints = item.path_node_ids.map((id) => nodes.get(id));
    const currentPoints = proposal.current_path_node_ids.map((id) => nodes.get(id));
    if (proposedPoints.length < 2 || proposedPoints.some((point) => !point || !Number.isFinite(point.lon))) continue;
    if (currentPoints.some((point) => !point || !Number.isFinite(point.lon))) continue;
    const proposed = polyline(proposedPoints as LineEndpoint[], legPath);
    const current = currentPoints.length >= 2
      ? polyline(currentPoints as LineEndpoint[], legPath)
      : currentPoints.map((point) => [point!.lon, point!.lat] as LineCoordinate);
    out.push({
      id: `book-proposal-${item.opportunity_id}`,
      opportunityId: item.opportunity_id,
      current,
      proposed,
      label: benefitLabel(item, t),
      labelAt: pointAtFraction(proposed, 0.5) ?? proposed[0],
    });
  }
  return out;
}
