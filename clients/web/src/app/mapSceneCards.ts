import type { MapAssetDTO, MapCargoDTO } from "@/api/client";
import { STALE_AFTER_HOURS, assetFigures, cargoPositions, figureAgeHours } from "./mapScene.ts";

/**
 * The hover cards of the map scene (MAP-1): every figure with its source, its gas day and how
 * old it is; an estimate says it is one; a country's inventory says it is not the site's.
 * Pure text builders (tests/mapScene.test.ts); the map escapes and places them.
 */

export type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface CardText {
  title: string;
  /** One line each; the first is the main figure. */
  lines: string[];
  /** The note under the figures: what the drawing means (estimated, not to scale...). */
  note: string | null;
}

/** "3 h" / "2 d" ago, or "age unknown". */
export function ageText(hours: number | null, t: Translate): string {
  if (hours === null) return t("map.scene.age_unknown");
  if (hours < 1) return t("map.scene.age_minutes", { count: Math.max(1, Math.round(hours * 60)) });
  if (hours < 48) return t("map.scene.age_hours", { count: Math.round(hours) });
  return t("map.scene.age_days", { count: Math.round(hours / 24) });
}

/** The source and freshness that follow every figure: "ENTSOG, gas day 2026-11-12, received 3 h ago". */
export function provenanceText(
  source: string,
  gasDay: string | null,
  receivedAtUtc: string | null,
  now: Date,
  t: Translate,
): string {
  const hours = figureAgeHours(receivedAtUtc, now);
  const parts = [source];
  if (gasDay) parts.push(t("map.scene.gas_day", { day: gasDay }));
  if (receivedAtUtc) parts.push(t("map.scene.received", { age: ageText(hours, t) }));
  const text = parts.join(", ");
  return hours !== null && hours > STALE_AFTER_HOURS ? `${text} · ${t("map.scene.stale")}` : text;
}

const gwh = (value: number) => `${Math.round(value).toLocaleString("en-GB")} GWh/d`;
const twh = (value: number) => `${(Math.round(value * 100) / 100).toLocaleString("en-GB")} TWh`;

function directionWord(kind: MapAssetDTO["kind"], direction: string, t: Translate): string {
  // At a storage point, entry into the grid is withdrawal from storage and exit is injection.
  if (kind === "storage") return t(direction === "entry" ? "map.scene.dir.withdrawal" : "map.scene.dir.injection");
  return t(direction === "entry" ? "map.scene.dir.send_out" : "map.scene.dir.exit");
}

export function assetCard(asset: MapAssetDTO, now: Date, t: Translate, dimension: "2d" | "3d"): CardText {
  const figures = assetFigures(asset);
  const lines: string[] = [];
  const capacity = asset.capacity.find((item) => item.direction === figures.capacityDirection) ?? null;
  if (capacity && figures.capacityGwhD !== null) {
    lines.push(t("map.scene.capacity", {
      direction: directionWord(asset.kind, capacity.direction, t),
      value: gwh(capacity.gwh_d),
      provenance: provenanceText(t("map.scene.src.entsog_capacity", { source: capacity.source_system }), capacity.gas_day, capacity.observed_at_utc, now, t),
    }));
  } else {
    lines.push(t("map.scene.no_capacity"));
  }
  for (const flow of asset.flow) {
    const share = figures.capacityGwhD !== null && flow.direction === figures.capacityDirection
      ? ` · ${t("map.scene.of_capacity", { pct: Math.round((flow.gwh_d / figures.capacityGwhD) * 100) })}`
      : "";
    lines.push(t("map.scene.flow", {
      direction: directionWord(asset.kind, flow.direction, t),
      value: gwh(flow.gwh_d),
      provenance: provenanceText(t("map.scene.src.entsog_flow", { source: flow.source_system }), flow.gas_day, null, now, t),
    }) + share);
  }
  const stock = asset.stock;
  if (stock && stock.inventory_twh !== null) {
    const max = asset.kind === "storage" ? stock.working_capacity_twh : stock.dtmi_twh;
    const scope = stock.basis === "site"
      ? t("map.scene.stock_site")
      : t("map.scene.stock_country", { country: stock.scope });
    lines.push(t(max ? "map.scene.stock_of" : "map.scene.stock", {
      scope,
      value: twh(stock.inventory_twh),
      max: max ? twh(max) : "",
      provenance: provenanceText(`${stock.source_system} ${stock.dataset}`, stock.gas_day, stock.observed_at_utc, now, t),
    }));
  } else {
    lines.push(t("map.scene.no_stock"));
  }
  const notes = [t("map.scene.position_approx")];
  if (dimension === "3d") notes.push(t("map.scene.column_note"));
  return {
    title: `${asset.name} · ${t(asset.kind === "storage" ? "map.scene.kind.storage" : "map.scene.kind.lng_terminal")}`,
    lines,
    note: notes.join(" "),
  };
}

/** An instant as the reader's formatter writes it (app/time/timeFormat.ts, via the map). */
export type FormatInstant = (iso: string) => string;

function etaLine(cargo: MapCargoDTO, t: Translate, when: FormatInstant): string {
  if (!cargo.eta_utc) return t("map.scene.eta_none");
  const basis = cargo.eta?.basis ? t(`map.scene.eta_basis.${cargo.eta.basis}`) : t("map.scene.eta_basis.none");
  const confidence = cargo.eta?.confidence ? t(`map.scene.eta_confidence.${cargo.eta.confidence}`) : t("map.scene.eta_confidence.none");
  return t("map.scene.eta", {
    when: when(cargo.eta_utc),
    terminal: cargo.destination_terminal ?? "",
    basis,
    confidence,
    source: cargo.eta?.source ?? cargo.source_system,
  });
}

/** The card of a cargo's estimated position: an interpolation, never an observation. */
export function estimateCard(cargo: MapCargoDTO, now: Date, t: Translate, when: FormatInstant): CardText | null {
  const { estimate } = cargoPositions(cargo, now);
  if (!estimate) return null;
  const from = estimate.from === "reported"
    ? t("map.scene.estimate_from_report", { age: ageText(figureAgeHours(cargo.position_at_utc, now), t) })
    : t("map.scene.estimate_from_departure", { port: cargo.load_port });
  return {
    title: `${cargo.vessel_name} · ${t("map.scene.estimated_position")}`,
    lines: [etaLine(cargo, t, when)],
    note: t("map.scene.estimate_note", { from, terminal: cargo.destination_terminal ?? "" }),
  };
}

/** The card of a voyage drawn without a reported track: origin to destination, not a route. */
export function voyageCard(cargo: MapCargoDTO, t: Translate, when: FormatInstant): CardText {
  return {
    title: `${cargo.vessel_name} · ${cargo.load_port} → ${cargo.destination_terminal ?? ""}`,
    lines: [etaLine(cargo, t, when)],
    note: t("map.scene.voyage_note"),
  };
}

/** The card of a flow line: the figure, its day and source, and what the direction rests on. */
export function flowCard(
  props: { name: string; direction: string; gwh_d: number; gas_day: string | null; operator?: string | null; source?: string | null },
  t: Translate,
): CardText {
  return {
    title: props.name,
    lines: [t("map.scene.flow_line", { value: gwh(props.gwh_d), day: props.gas_day ?? "" })],
    note: t("map.scene.flow_note", { source: props.source ?? "ENTSOG" }),
  };
}
